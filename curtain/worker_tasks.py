import io

import numpy as np
import pandas as pd
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django_rq import job
from uniprotparser.betaparser import UniprotSequence, UniprotParser
import requests as req
from curtain.models import Curtain


@job("default")
def compare_session(id_list, study_list, match_type, session_id):
    to_be_processed_list = Curtain.objects.filter(link_id__in=id_list)
    result = {}
    raw_df_map = {}
    sample_map = {}
    raw_form_map = {}
    uniprot_id_list = []
    study_map = {}
    channel_layer = get_channel_layer()
    message_template = {
        'message': "",
        'senderName': "Server",
        'requestType': "Compare Session",
        'operationId': ""
    }
    if match_type == "primaryID-uniprot" or match_type == "geneNames":
        for i in study_list:
            if UniprotSequence(i, parse_acc=True).accession:
                study_map[UniprotSequence(i, parse_acc=True).accession] = i

        uniprot_id_list.extend(study_map.keys())
    data_store_dict = {}
    comparison_dict = {}
    for i in to_be_processed_list:
        message_template["message"] = "Processing " + i.link_id
        async_to_sync(channel_layer.group_send)(session_id, {
            'type': 'job_message',
            'message': message_template
        })
        data = req.get(i.file.url).json()
        differential_form = data["differentialForm"]
        raw_form_map[i.link_id] = data["rawForm"]
        print(data["settings"])
        sample_map[i.link_id] = data["settings"]["sampleMap"]
        pid_col = differential_form["_primaryIDs"]
        fc_col = differential_form["_foldChange"]
        significant_col = differential_form["_significant"]
        string_data = io.StringIO(data["processed"])
        raw_string_data = io.StringIO(data["raw"])
        df = pd.read_csv(string_data, sep="\t")
        raw_df = pd.read_csv(raw_string_data, sep="\t")
        raw_df_map[i.link_id] = raw_df
        comparison_col = differential_form["_comparison"]
        comparisons = []
        if len(differential_form["_comparisonSelect"]) > 0:
            if differential_form["_comparison"] in df.columns:
                df[differential_form["_comparison"]] = df[differential_form["_comparison"]].astype(str)
                if type(differential_form["_comparisonSelect"]) == str:
                    df = df[df[comparison_col] == differential_form["_comparisonSelect"]]
                    comparisons.append(differential_form["_comparisonSelect"])
                else:
                    df = df[df[comparison_col].isin(differential_form["_comparisonSelect"])]
                    comparisons.extend(differential_form["_comparisonSelect"])
        comparison_dict[i.link_id] = comparisons
        if differential_form["_transformFC"]:
            df[fc_col].apply(lambda x: np.log2(x) if x >= 0 else -np.log2(-x))
        if differential_form["_transformSignificant"]:
            df[significant_col] = -np.log10(df[significant_col])
        if match_type == "primaryID":
            message_template["message"] = "Matching Primary ID for " + i.link_id
            async_to_sync(channel_layer.group_send)(session_id, {
                'type': 'job_message',
                'message': message_template
            })
            df = df[df[pid_col].isin(study_list)]
            cols = [pid_col, fc_col, significant_col]
            if len(comparisons) > 0:
                cols.append(comparison_col)
            df = df[cols]
            df["source_pid"] = df[pid_col]
            if len(comparisons) > 0:
                df.rename(columns={pid_col: "primaryID", fc_col: "foldChange", significant_col: "significant", comparison_col: "comparison"},
                          inplace=True)
            else:
                df.rename(columns={pid_col: "primaryID", fc_col: "foldChange", significant_col: "significant"},
                          inplace=True)
            result[i.link_id]["differential"] = df
        elif match_type == "primaryID-uniprot":
            message_template["message"] = "Matching UniProt Primary ID for " + i.link_id
            async_to_sync(channel_layer.group_send)(session_id, {
                'type': 'job_message',
                'message': message_template
            })
            df["curtain_uniprot"] = df[pid_col].apply(
                lambda x: UniprotSequence(x, parse_acc=True).accession if UniprotSequence(x,
                                                                                          parse_acc=True).accession else x)
            df = df[df["curtain_uniprot"].isin(uniprot_id_list)]
            cols = [pid_col,  "curtain_uniprot", fc_col, significant_col]
            if len(comparisons) > 0:
                cols.append(comparison_col)
            df = df[cols]
            df["source_pid"] = df["curtain_uniprot"].apply(lambda x: study_map[x] if x in study_map else None)
            if len(comparisons) > 0:
                df.rename(columns={pid_col: "primaryID", "curtain_uniprot": "uniprot", fc_col: "foldChange",
                                   significant_col: "significant", comparison_col: "comparison"}, inplace=True)
            else:
                df.rename(columns={pid_col: "primaryID", "curtain_uniprot": "uniprot", fc_col: "foldChange",
                                   significant_col: "significant"}, inplace=True)
            result[i.link_id]["differential"] = df
        elif match_type == "geneNames":
            df["curtain_uniprot"] = df[pid_col].apply(
                lambda x: UniprotSequence(x, parse_acc=True).accession if UniprotSequence(x,parse_acc=True).accession else x)
            if len(comparisons) > 0:
                df.rename(columns={pid_col: "primaryID", "curtain_uniprot": "uniprot", fc_col: "foldChange", comparison_col: "comparison", significant_col: "significant"}, inplace=True)
            else:
                df.rename(columns={pid_col: "primaryID", "curtain_uniprot": "uniprot", fc_col: "foldChange", significant_col: "significant"}, inplace=True)
            data_store_dict[i.link_id] = df
            uniprot_id_list.extend(df["uniprot"].tolist())


    if match_type == "geneNames":
        unique_uniprot = set(uniprot_id_list)
        parser = UniprotParser(columns="accession,id,gene_names")
        uni_df = []
        message_template["message"] = "Retrieving UniProt data"
        async_to_sync(channel_layer.group_send)(session_id, {
            'type': 'job_message',
            'message': message_template
        })
        job_number = 0
        for p in parser.parse(unique_uniprot):
            uniprot_df = pd.read_csv(io.StringIO(p), sep="\t")
            uni_df.append(uniprot_df)
            message_template["message"] = "Downloaded UniProt Job " + str(job_number+1)
            async_to_sync(channel_layer.group_send)(session_id, {
                'type': 'job_message',
                'message': message_template
            })
            job_number += 1
        if len(uni_df) == 1:
            uni_df = uni_df[0]
        else:
            uni_df = pd.concat(uni_df, ignore_index=True)
        studied_uni_df = uni_df[uni_df["From"].isin(set(study_map.keys()))]
        # studied_uni_df["gene_names_split"] = studied_uni_df["Gene Names"].str.split(" ")
        # studied_uni_df = studied_uni_df.explode("gene_names_split")
        for i in data_store_dict:
            stored_df = data_store_dict[i]
            stored_df = stored_df.merge(uni_df, left_on="uniprot", right_on="From", how="left")
            stored_df["Gene Names"] = stored_df["Gene Names"].str.upper()
            stored_df["gene_names_split"] = stored_df["Gene Names"].str.split(" ")
            stored_df = stored_df.explode("gene_names_split", ignore_index=True)
            fin_df = []
            message_template["message"] = "Matching Gene Names for " + i
            async_to_sync(channel_layer.group_send)(session_id, {
                'type': 'job_message',
                'message': message_template
            })
            for i2, r in studied_uni_df.iterrows():

                if pd.notnull(r["Gene Names"]):
                    for g in r["Gene Names"].split(" "):
                        if g in stored_df["gene_names_split"].values:
                            stored_result = stored_df[stored_df["gene_names_split"] == g]
                            stored_result["source_pid"] = study_map[r["From"]]
                            fin_df.append(stored_result)
                            break
            if len(fin_df) == 1:
                fin_df = fin_df[0]
            else:
                fin_df = pd.concat(fin_df, ignore_index=True)
            cols = ["primaryID", "uniprot", "foldChange", "significant", "source_pid", "Gene Names"]
            if i in comparison_dict:
                if len(comparison_dict[i]) > 0:
                    cols.append("comparison")
            fin_df = fin_df[cols]
            result[i]["differential"] = fin_df

    for i in result:
        raw = raw_df_map[i]
        raw = raw[raw[raw_form_map[i]["_primaryIDs"]].isin(result[i]["differential"]["primaryID"].tolist())]
        raw_cols = []
        for s in sample_map[i]:
            raw_cols.append(s)
        raw_cols.append(raw_form_map[i]["_primaryIDs"])
        raw = raw[raw_cols]
        raw.rename(columns={raw_form_map[i]["_primaryIDs"]: "primaryID"}, inplace=True)
        result[i]["raw"] = raw.to_dict(orient="records")
        result[i]["differential"] = result[i]["differential"].to_dict(orient="records")
        result[i]["sampleMap"] = sample_map[i]

    message_template["message"] = "Operation Completed"
    message_template["data"] = result
    async_to_sync(channel_layer.group_send)(session_id, {
        'type': 'job_message',
        'message': message_template
    })
    return result