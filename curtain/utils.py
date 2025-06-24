import base64
import io
import json

import globus_sdk
import numpy as np
import pandas as pd
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework_simplejwt.tokens import AccessToken
from uniprotparser.betaparser import UniprotParser


def get_user_from_token(request):
    if 'HTTP_AUTHORIZATION' in request.META:
        authorization = request.META['HTTP_AUTHORIZATION'].replace("Bearer ", "")
        access_token = AccessToken(authorization)
        user = User.objects.filter(pk=access_token["user_id"]).first()
        if user:
            return user
    return


def is_user_staff(request):
    user = request.user
    if not user:
        user = get_user_from_token(request)
    if user:
        if user.is_staff:
            return True
    return False


def delete_file_related_objects(file):
    for c in file.comparisons.all():
        with transaction.atomic():
            for column in c.differential_sample_columns.all():
                column.delete()
            for da in c.differential_analysis_datas.all():
                da.delete()
    with transaction.atomic():
        for r in file.raw_datas.all():
            r.delete()
    for rc in file.raw_sample_columns.all():
        with transaction.atomic():
            rc.delete()


def calculate_boxplot_parameters(values):
    q1, med, q3 = np.percentile(values, [25, 50, 75])

    iqr = q3 - q1

    low = q1 - 1.5 * iqr
    high = q3 + 1.5 * iqr

    wisker_high = np.compress(values <= high, values)
    wisker_low = np.compress(values >= low, values)

    real_high_val = np.max(wisker_high)
    real_low_val = np.min(wisker_low)

    return {"low": real_low_val, "q1": q1, "med": med, "q3": q3, "high": real_high_val}

def check_nan_return_none(value):
    if pd.notnull(value):
        return value
    return None

def get_uniprot_data(df, column_name):
    primary_id = df[column_name].str.split(";")
    primary_id = primary_id.explode().unique()
    parser = UniprotParser()
    uni_df = []
    for p in parser.parse(primary_id):
        uniprot_df = pd.read_csv(io.StringIO(p), sep="\t")
        uni_df.append(uniprot_df)
    if len(uni_df) == 1:
        uni_df = uni_df[0]
    elif len(uni_df) > 1:
        uni_df = pd.concat(uni_df, ignore_index=True)
    else:
        return pd.DataFrame()
    uni_df.set_index("From", inplace=True)
    return uni_df

def encrypt_data(public_key, data: bytes):
    loaded_key = serialization.load_pem_public_key(
        public_key,
        backend=default_backend()
    )
    encrypted = base64.b64encode(loaded_key.encrypt(
        data,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    ))
    return encrypted

def get_globus_access_token(globus_refresh_token: str, globus_client_id: str):
    client = globus_sdk.NativeAppAuthClient(globus_client_id)
    token_response = client.oauth2_refresh_token(globus_refresh_token)
    return token_response["access_token"]

