import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inilint import Problem, fix_text, lint_file, lint_text


class TestCleanFile(unittest.TestCase):
    def test_no_problems(self):
        text = "[server]\nhost = localhost\nport = 8080\n"
        self.assertEqual(lint_text(text), [])


class TestSectionHeaders(unittest.TestCase):
    def test_unterminated_section_header(self):
        text = "[server\n"
        problems = lint_text(text)
        self.assertEqual(
            problems,
            [Problem(1, 8, "unterminated section header, expected closing ']'")],
        )

    def test_empty_section_name(self):
        text = "[]\n"
        problems = lint_text(text)
        self.assertEqual(problems, [Problem(1, 2, "section name cannot be empty")])

    def test_duplicate_section(self):
        text = "[server]\nhost = localhost\n\n[server]\ntimeout = 30\n"
        problems = lint_text(text)
        self.assertEqual(
            problems,
            [Problem(4, 1, "duplicate section 'server' (first defined at line 1)")],
        )

    def test_inline_comment_on_header_not_unterminated(self):
        text = "[server] ; the main one\nhost = localhost\n"
        self.assertEqual(lint_text(text), [])


class TestKeyValueLines(unittest.TestCase):
    def test_missing_key_before_separator(self):
        text = "[server]\n= value\n"
        problems = lint_text(text)
        self.assertEqual(problems, [Problem(2, 1, "missing key before '='")])

    def test_key_outside_section(self):
        text = "port = 8080\n"
        problems = lint_text(text)
        self.assertEqual(
            problems, [Problem(1, 1, "key 'port' is outside of any section")]
        )

    def test_malformed_line(self):
        text = "[server]\njustsometext\n"
        problems = lint_text(text)
        self.assertEqual(
            problems,
            [Problem(2, 1, "expected 'key = value', a section header, or a comment")],
        )

    def test_duplicate_key_case_insensitive_by_default(self):
        text = "[server]\nPort = 8080\nport = 9090\n"
        problems = lint_text(text)
        self.assertEqual(
            problems,
            [
                Problem(
                    3, 1,
                    "duplicate key 'port' in section [server] "
                    "(first set at line 2)",
                )
            ],
        )

    def test_duplicate_key_not_flagged_in_strict_mode(self):
        text = "[server]\nPort = 8080\nport = 9090\n"
        self.assertEqual(lint_text(text, strict=True), [])


class TestContinuationLines(unittest.TestCase):
    def test_continuation_without_preceding_key(self):
        text = "[server]\n\n    continued\n"
        problems = lint_text(text)
        self.assertEqual(
            problems,
            [Problem(3, 5, "continuation line with no preceding 'key = value' line")],
        )

    def test_continuation_broken_by_comment(self):
        text = "[server]\nmotd = hi\n; a comment\n    continued\n"
        problems = lint_text(text)
        self.assertEqual(
            problems,
            [Problem(4, 5, "continuation line with no preceding 'key = value' line")],
        )

    def test_valid_multiline_value_has_no_problems(self):
        text = "[server]\nmotd = welcome to the server,\n    please be nice\n"
        self.assertEqual(lint_text(text), [])


class TestFixText(unittest.TestCase):
    def test_removes_duplicate_key_keeping_first(self):
        text = "[server]\nport = 8080\nport = 9090\n"
        fixed, removed = fix_text(text)
        self.assertEqual(removed, 1)
        self.assertEqual(fixed, "[server]\nport = 8080\n")

    def test_removes_continuation_lines_with_duplicate(self):
        text = (
            "[server]\n"
            "motd = hi\n"
            "motd = bye\n"
            "    still bye\n"
            "host = localhost\n"
        )
        fixed, removed = fix_text(text)
        self.assertEqual(removed, 1)
        self.assertEqual(fixed, "[server]\nmotd = hi\nhost = localhost\n")

    def test_duplicate_key_case_insensitive_by_default(self):
        text = "[server]\nPort = 8080\nport = 9090\n"
        fixed, removed = fix_text(text)
        self.assertEqual(removed, 1)
        self.assertEqual(fixed, "[server]\nPort = 8080\n")

    def test_strict_mode_treats_different_case_as_distinct_keys(self):
        text = "[server]\nPort = 8080\nport = 9090\n"
        fixed, removed = fix_text(text, strict=True)
        self.assertEqual(removed, 0)
        self.assertEqual(fixed, text)

    def test_no_duplicates_leaves_file_unchanged(self):
        text = "[server]\nhost = localhost\nport = 8080\n"
        fixed, removed = fix_text(text)
        self.assertEqual(removed, 0)
        self.assertEqual(fixed, text)

    def test_duplicates_in_separate_sections_are_kept(self):
        text = "[a]\nhost = localhost\n\n[b]\nhost = otherhost\n"
        fixed, removed = fix_text(text)
        self.assertEqual(removed, 0)
        self.assertEqual(fixed, text)

    def test_removes_multiple_duplicates(self):
        text = "[server]\nhost = a\nhost = b\nport = 1\nport = 2\n"
        fixed, removed = fix_text(text)
        self.assertEqual(removed, 2)
        self.assertEqual(fixed, "[server]\nhost = a\nport = 1\n")


class TestLintFile(unittest.TestCase):
    def test_reads_and_lints_a_file_on_disk(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ini", delete=False, encoding="utf-8"
        ) as f:
            f.write("[server]\nhost = localhost\n\n[server]\n")
            path = f.name
        try:
            problems = lint_file(path)
            self.assertEqual(
                problems,
                [
                    Problem(
                        4, 1,
                        "duplicate section 'server' (first defined at line 1)",
                    )
                ],
            )
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
