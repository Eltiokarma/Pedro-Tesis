"""Exercise the public headless workflow and protect measured input files."""
import json

import dynamic_cli


def test_example_template_and_headless_exports(tmp_path):
    case_path = tmp_path / "case.json"
    measured_path = tmp_path / "measured.csv"
    assert dynamic_cli.main(["--write-example", str(case_path),
                             "--measurement-template", str(measured_path)]) == 0
    assert len(measured_path.read_text(encoding="utf-8").splitlines()) == 1
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["simulation"]["duration_s"] = 10.0
    case["events"] = []
    case_path.write_text(json.dumps(case), encoding="utf-8")
    result_path, csv_path = tmp_path / "run.json", tmp_path / "run.csv"
    assert dynamic_cli.main([str(case_path), "--out", str(result_path), "--csv", str(csv_path)]) == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["summary"]["success"]
    assert result["series"][-1]["time_s"] == 10.0
    assert "tank_temperature_K" in csv_path.read_text(encoding="utf-8").splitlines()[0]


def test_refuses_to_overwrite_input_or_share_outputs(tmp_path):
    path = tmp_path / "case.json"
    path.write_text("{\"preserve\": true}", encoding="utf-8")
    before = path.read_bytes()
    assert dynamic_cli.main([str(path), "--out", str(path)]) == 2
    assert path.read_bytes() == before
    assert dynamic_cli.main(["--out", str(path), "--csv", str(path)]) == 2
    assert path.read_bytes() == before


def test_bad_case_has_nonzero_exit(tmp_path, capsys):
    path = tmp_path / "case.json"
    path.write_text("not json", encoding="utf-8")
    assert dynamic_cli.main([str(path)]) == 2
    assert "Error:" in capsys.readouterr().err
