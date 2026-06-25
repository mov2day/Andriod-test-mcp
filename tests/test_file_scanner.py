import pytest
from pathlib import Path
from core.file_scanner import FileScanner

def test_file_scanner_discovery(tmp_path):
    # Create mock repo structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')")
    (tmp_path / "src" / "test_main.py").write_text("def test_main(): pass")
    
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_utils.py").write_text("def test_util(): pass")
    
    (tmp_path / ".gitignore").write_text("ignored.py")
    (tmp_path / "ignored.py").write_text("print('ignore me')")
    
    scanner = FileScanner(tmp_path)
    
    source_files = scanner.discover_source_files(["**/*.py"], exclude_patterns=["**/test_*"])
    assert len(source_files) == 1
    assert "src/main.py" in source_files[0]
    
    test_files = scanner.find_test_files(["**/test_*.py"])
    assert len(test_files) == 2

def test_file_scanner_pairing():
    scanner = FileScanner(".")
    source_files = ["src/api/auth.py", "src/utils/math.py"]
    test_files = ["tests/unit/api/test_auth.py", "tests/integration/test_math.py"]
    
    pairs = scanner.pair_source_to_test(source_files, test_files, "test_{name}.py")
    
    assert pairs["src/api/auth.py"] == "tests/unit/api/test_auth.py"
    assert pairs["src/utils/math.py"] == "tests/integration/test_math.py"
