import json
import csv
import sys
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from curtain.models import Curtain


class Command(BaseCommand):
    """
    Search curtain sessions by filtering on metadata embedded in the uploaded file.

    The uploaded file is a JSON object with this shape (serialized from the Angular frontend):

        {
            "raw":             "<TSV string>",
            "rawForm":         { "_primaryIDs": "...", "_samples": [...], "_log2": false },
            "differentialForm": {
                "_primaryIDs":          "...",
                "_foldChange":          "...",
                "_significant":         "...",
                "_comparison":          "Comparison",        <- column name in CSV, NOT the value
                "_comparisonSelect":    ["ip.B.minus.AL-ip.B.plus.AL"],   <- selected value(s)
                                                               TP = string[], PTM = string
                "_transformFC":         false,
                "_transformSignificant":false,
                "_reverseFoldChange":   false,
                ...
            },
            "processed":       "<TSV string>",
            "password":        "",
            "selections":      [...],
            "settings": {
                "description":        "...",
                "currentComparison":  "ip.B.minus.AL-ip.B.plus.AL",   <- active comparison
                "selectedComparison": ["ip.B.minus.AL-ip.B.plus.AL"],  <- selected list
                "pCutoff":            0.05,
                "log2FCCutoff":       0.6,
                "fetchUniprot":       true,
                ...
            },
            ...
        }

    The comparison value to search on is `differentialForm._comparisonSelect`.
    For PTM sessions this is a plain string; for TP sessions it is an array.
    `settings.currentComparison` is used as a fallback.
    """

    help = "Search curtain sessions by settings fields and date range"

    def add_arguments(self, parser):
        # ---- date range ----
        parser.add_argument(
            "--from-date",
            type=str,
            default=None,
            help="Include sessions created on or after this date (YYYY-MM-DD)",
        )
        parser.add_argument(
            "--to-date",
            type=str,
            default=None,
            help="Include sessions created on or before this date (YYYY-MM-DD)",
        )

        # ---- Curtain model fields ----
        parser.add_argument(
            "--curtain-type",
            type=str,
            choices=["TP", "PTM", "F"],
            default=None,
            help="Filter by curtain type: TP, PTM, or F",
        )
        parser.add_argument(
            "--owner",
            type=str,
            default=None,
            help="Filter by owner username (exact match)",
        )

        # ---- comparison filters ----
        parser.add_argument(
            "--comparison",
            type=str,
            default=None,
            help=(
                "Exact match on differentialForm._comparisonSelect "
                "(or settings.currentComparison as fallback)"
            ),
        )
        parser.add_argument(
            "--comparison-contains",
            type=str,
            default=None,
            help="Substring match (case-insensitive) on the comparison value",
        )

        # ---- settings filters ----
        parser.add_argument(
            "--description-contains",
            type=str,
            default=None,
            help="Substring match (case-insensitive) on settings.description",
        )
        parser.add_argument(
            "--uniprot",
            action="store_true",
            default=False,
            help="Only include sessions where settings.fetchUniprot is true",
        )

        # ---- output ----
        parser.add_argument(
            "--output-format",
            type=str,
            choices=["table", "json", "csv"],
            default="table",
            help="Output format (default: table)",
        )
        parser.add_argument(
            "--output-file",
            type=str,
            default=None,
            help="Write results to this file path instead of stdout",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Stop after returning this many matches",
        )
        parser.add_argument(
            "--skip-errors",
            action="store_true",
            default=False,
            help="Skip sessions whose files cannot be read/parsed instead of aborting",
        )
        parser.add_argument(
            "--include-encrypted",
            action="store_true",
            default=False,
            help="Attempt to process encrypted sessions (will likely fail to parse)",
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _parse_date(self, value, field_name):
        try:
            dt = datetime.strptime(value, "%Y-%m-%d")
            return timezone.make_aware(dt)
        except ValueError:
            raise CommandError(f"--{field_name}: expected YYYY-MM-DD, got '{value}'")

    def _load_file(self, curtain):
        """Return the decoded JSON dict from the session file, or raise ValueError."""
        if not curtain.file or not curtain.file.name:
            raise ValueError("no file attached to this session")
        try:
            with curtain.file.open("rb") as fh:
                return json.load(fh)
        except FileNotFoundError:
            raise ValueError(f"file not found on storage: {curtain.file.name}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"file is not valid JSON (possibly encrypted): {exc}") from exc
        except Exception as exc:
            raise ValueError(f"cannot open file: {exc}") from exc

    def _get_settings(self, data):
        """
        Return settings as a dict.
        Current frontend stores it as a plain object.
        Very old sessions stored it as a JSON-encoded string — handle both.
        """
        raw = data.get("settings", {})
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}
        return raw if isinstance(raw, dict) else {}

    def _get_comparison_values(self, data):
        """
        Return a list of comparison values for this session.

        Priority:
          1. differentialForm._comparisonSelect  (TP = list, PTM = string)
          2. settings.currentComparison          (string fallback)
          3. settings.selectedComparison         (list fallback)
        """
        diff_form = data.get("differentialForm", {})
        comp_select = diff_form.get("_comparisonSelect")

        if comp_select is not None:
            if isinstance(comp_select, list):
                values = [str(v) for v in comp_select if v]
            else:
                values = [str(comp_select)] if comp_select else []
            if values:
                return values

        # fallback to settings
        settings = self._get_settings(data)
        current = settings.get("currentComparison", "")
        if current:
            return [current]

        selected = settings.get("selectedComparison", [])
        if isinstance(selected, list):
            return [str(v) for v in selected if v]
        return []

    def _matches(self, data, options):
        comparison_values = self._get_comparison_values(data)
        if options["comparison"] is not None:
            # exact match: the filter must equal one of the comparison values
            if options["comparison"] not in comparison_values:
                return False

        if options["comparison_contains"] is not None:
            needle = options["comparison_contains"].lower()
            if not any(needle in v.lower() for v in comparison_values):
                return False

        if options["description_contains"] is not None:
            settings = self._get_settings(data)
            desc = settings.get("description", "")
            if options["description_contains"].lower() not in desc.lower():
                return False

        if options["uniprot"]:
            settings = self._get_settings(data)
            if not settings.get("fetchUniprot", False):
                return False

        return True

    def _build_row(self, curtain, data):
        settings = self._get_settings(data)
        diff_form = data.get("differentialForm", {})
        owners = ", ".join(curtain.owners.values_list("username", flat=True))
        comparison_values = self._get_comparison_values(data)
        return {
            "link_id": curtain.link_id,
            "curtain_type": curtain.curtain_type,
            "created": curtain.created.strftime("%Y-%m-%d %H:%M:%S"),
            "owners": owners,
            "description": settings.get("description", ""),
            "comparison_col": diff_form.get("_comparison", ""),
            "comparison_select": ", ".join(comparison_values),
            "p_cutoff": settings.get("pCutoff", ""),
            "log2fc_cutoff": settings.get("log2FCCutoff", ""),
            "fetch_uniprot": settings.get("fetchUniprot", ""),
        }

    # ------------------------------------------------------------------
    # output renderers
    # ------------------------------------------------------------------

    def _write_table(self, rows, out):
        if not rows:
            out.write("No matching sessions found.\n")
            return
        cols = list(rows[0].keys())
        widths = {c: max(len(str(c)), max(len(str(r[c])) for r in rows)) for c in cols}
        header = "  ".join(str(c).ljust(widths[c]) for c in cols)
        sep = "  ".join("-" * widths[c] for c in cols)
        out.write(header + "\n")
        out.write(sep + "\n")
        for row in rows:
            out.write("  ".join(str(row[c]).ljust(widths[c]) for c in cols) + "\n")

    def _write_json(self, rows, out):
        json.dump(rows, out, indent=2, default=str)
        out.write("\n")

    def _write_csv(self, rows, out):
        if not rows:
            return
        writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    def _render(self, fmt, rows, out):
        if fmt == "table":
            self._write_table(rows, out)
        elif fmt == "json":
            self._write_json(rows, out)
        elif fmt == "csv":
            self._write_csv(rows, out)

    # ------------------------------------------------------------------
    # handle
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        qs = Curtain.objects.prefetch_related("owners").order_by("created")

        if options["from_date"]:
            qs = qs.filter(created__gte=self._parse_date(options["from_date"], "from-date"))
        if options["to_date"]:
            qs = qs.filter(created__lte=self._parse_date(options["to_date"], "to-date"))
        if options["curtain_type"]:
            qs = qs.filter(curtain_type=options["curtain_type"])
        if options["owner"]:
            qs = qs.filter(owners__username=options["owner"])
        if not options["include_encrypted"]:
            qs = qs.filter(encrypted=False)

        total = qs.count()
        self.stderr.write(f"Found {total} session(s) to scan.\n")

        rows = []
        scanned = skipped_encrypted = errors = 0
        progress_interval = max(1, total // 20)  # update every ~5%

        for curtain in qs.iterator(chunk_size=100):
            if options["limit"] and len(rows) >= options["limit"]:
                break

            scanned += 1

            if scanned == 1 or scanned % progress_interval == 0 or scanned == total:
                pct = scanned * 100 // total if total else 100
                self.stderr.write(
                    f"\rProgress: {scanned}/{total} ({pct}%)  "
                    f"matched={len(rows)}  errors={errors}",
                    ending="",
                )
                self.stderr.flush()

            if curtain.encrypted and not options["include_encrypted"]:
                skipped_encrypted += 1
                continue

            try:
                data = self._load_file(curtain)
            except ValueError as exc:
                if options["skip_errors"]:
                    self.stderr.write(f"\n[skip] {curtain.link_id}: {exc}")
                    errors += 1
                    continue
                self.stderr.write("")  # newline after progress line
                raise CommandError(str(exc)) from exc

            if self._matches(data, options):
                rows.append(self._build_row(curtain, data))

        self.stderr.write(
            f"\nDone. Scanned {scanned} | matched {len(rows)} | "
            f"errors {errors} | encrypted skipped {skipped_encrypted}"
        )

        out_path = options["output_file"]
        fmt = options["output_format"]

        if out_path:
            with open(out_path, "w", newline="", encoding="utf-8") as fh:
                self._render(fmt, rows, fh)
            self.stdout.write(f"Results written to {out_path}")
        else:
            self._render(fmt, rows, sys.stdout)
