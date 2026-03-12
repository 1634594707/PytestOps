# ntf-sample-plugin

Sample plugin pack for PytestOps (`ntf`). It demonstrates all plugin entry-points:

- `ntf.assertions` (custom assertion)
- `ntf.functions` (custom renderer functions)
- `ntf.reporters` (custom report output)
- `ntf.transports` (custom transport factory)
- `ntf.renderers` (custom renderer)

## Install (local)

```bash
cd plugins/ntf_sample_plugin
python -m pip install -e .
```

## Usage

### Custom assertion: `startswith`

```yaml
validate:
  - startswith: {"body.message": "ok"}
```

### Custom functions

```yaml
request:
  json:
    ts: "${now_iso()}"
    rid: "${rand_int(1000,9999)}"
```

### Custom reporter

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data --reporter print
```

Optionally write JSON report with:

```bash
set NTF_SAMPLE_REPORT=report/sample-plugin.json
```

### Custom transport

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data --transport requests_no_session
```

### Custom renderer

```bash
ntf run-yaml --config configs/default.yaml --cases tests/data --renderer upper
```
