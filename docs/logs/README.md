# Railway / production logs

Place exported Railway log files here for analysis, e.g.:

```text
docs/logs/logs.1779633652056.log
```

Then run:

```bash
python3 scripts/analyze_railway_logs.py docs/logs/logs.1779633652056.log
```

Output is written to `docs/BACKEND_LOG_TRIAGE.md` (regenerated).
