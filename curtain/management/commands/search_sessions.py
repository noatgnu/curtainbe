import json
import csv
import sys
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from curtain.models import Curtain


class Command(BaseCommand):
    """
    Search curtain sessions by filtering on metadata fields embedded in the uploaded file.

    The uploaded file for each session is a JSON blob with this top-level shape:
        {
            "raw": "...",
            "processed": "...",
            "settings": "{...}",   <- JSON string, parsed separately
            "password": "...",
            "selections": {...}
        }

    Inside settings the key paths used for filtering are:
        description                       - free-text session description
        dataColumns.comparison            - comparison label (e.g. "WT_vs_D1")
        dataColumns.processedCompLabel    - column name holding comparison values
        pCutOff                           - p-value cut-off used
        logFCCutOff                       - log-FC cut-off used
        uniprot                           - boolean, whether UniProt mapping was used

    Curtain-level fields that can also be filtered:
        curtain_type  - TP / PTM / F
        created       - creation timestamp (--from-date / --to-date)
        owners        - comma-separated usernames
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
            help="Filter by curtain type: TP (Total Proteomics), PTM, or F (Flex)",
        )
        parser.add_argument(
            "--owner",
            type=str,
            default=None,
            help="Filter by owner username (exact match)",
        )

        # ---- settings JSON fields ----
        parser.add_argument(
            "--comparison",
            type=str,
            default=None,
            help="Filter by settings.dataColumns.comparison (exact match)",
        )
        parser.add_argument(
            "--comparison-contains",
            type=str,
            default=None,
            help="Filter by settings.dataColumns.comparison (substring match)",
        )
        parser.add_argument(
            "--description-contains",
            type=str,
            default=None,
            help="Filter by settings.description (substring, case-insensitive)",
        )
        parser.add_argument(
            "--uniprot",
            action="store_true",
            default=None,
            help="Only include sessions where settings.uniprot is true",
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
            help="Write output to this file path instead of stdout",
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
            help="Skip sessions whose files cannot be read or parsed instead of aborting",
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

    def _read_session_file(self, curtain):
        """Return parsed outer dict and parsed settings dict, or raise."""
        with curtain.file.open("rb") as fh:
            outer = json.load(fh)
        raw_settings = outer.get("settings", "{}")
        if isinstance(raw_settings, str):
            settings = json.loads(raw_settings)
        else:
            settings = raw_settings
        return outer, settings

    def _matches(self, curtain, settings, options):
        """Return True if the session satisfies all active filters."""
        data_cols = settings.get("dataColumns", {})

        if options["comparison"] is not None:
            if data_cols.get("comparison") != options["comparison"]:
                return False

        if options["comparison_contains"] is not None:
            comp = data_cols.get("comparison", "")
            if options["comparison_contains"].lower() not in comp.lower():
                return False

        if options["description_contains"] is not None:
            desc = settings.get("description", "")
            if options["description_contains"].lower() not in desc.lower():
                return False

        if options["uniprot"]:
            if not settings.get("uniprot", False):
                return False

        return True

    def _build_row(self, curtain, settings):
        data_cols = settings.get("dataColumns", {})
        owners = ", ".join(curtain.owners.values_list("username", flat=True))
        return {
            "link_id": curtain.link_id,
            "curtain_type": curtain.curtain_type,
            "created": curtain.created.strftime("%Y-%m-%d %H:%M:%S"),
            "owners": owners,
            "description": settings.get("description", ""),
            "comparison": data_cols.get("comparison", ""),
            "comp_label_col": data_cols.get("processedCompLabel", ""),
            "p_cutoff": settings.get("pCutOff", ""),
            "logfc_cutoff": settings.get("logFCCutOff", ""),
            "uniprot": settings.get("uniprot", ""),
        }

    # ------------------------------------------------------------------
    # output renderers
    # ------------------------------------------------------------------

    def _write_table(self, rows, out):
        if not rows:
            out.write("No matching sessions found.\n")
            return
        cols = list(rows[0].keys())
        widths = {c: max(len(c), max(len(str(r[c])) for r in rows)) for c in cols}
        header = "  ".join(c.ljust(widths[c]) for c in cols)
        sep = "  ".join("-" * widths[c] for c in cols)
        out.write(header + "\n")
        out.write(sep + "\n")
        for row in rows:
            out.write("  ".join(str(row[c]).ljust(widths[c]) for c in cols) + "\n")

    def _write_json(self, rows, out):
        json.dump(rows, out, indent=2)
        out.write("\n")

    def _write_csv(self, rows, out):
        if not rows:
            return
        writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

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

        rows = []
        scanned = 0
        errors = 0

        for curtain in qs.iterator():
            if options["limit"] and len(rows) >= options["limit"]:
                break
            scanned += 1
            try:
                _outer, settings = self._read_session_file(curtain)
            except Exception as exc:
                if options["skip_errors"]:
                    self.stderr.write(f"[skip] {curtain.link_id}: {exc}")
                    errors += 1
                    continue
                raise CommandError(f"Failed to read session {curtain.link_id}: {exc}") from exc

            if self._matches(curtain, settings, options):
                rows.append(self._build_row(curtain, settings))

        self.stderr.write(
            f"Scanned {scanned} session(s), {len(rows)} match(es), {errors} error(s)."
        )

        out_path = options["output_file"]
        fmt = options["output_format"]

        if out_path:
            mode = "w"
            with open(out_path, mode, newline="", encoding="utf-8") as fh:
                self._render(fmt, rows, fh)
            self.stdout.write(f"Results written to {out_path}")
        else:
            self._render(fmt, rows, sys.stdout)

    def _render(self, fmt, rows, out):
        if fmt == "table":
            self._write_table(rows, out)
        elif fmt == "json":
            self._write_json(rows, out)
        elif fmt == "csv":
            self._write_csv(rows, out)
