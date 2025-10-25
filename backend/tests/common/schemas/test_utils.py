from app.common.schemas.utils import to_camel_case, to_snake_case


class TestToCamelCase:
    def test_single_word(self):
        assert to_camel_case("word") == "word"

    def test_two_words(self):
        assert to_camel_case("example_string") == "exampleString"

    def test_multiple_words(self):
        assert to_camel_case("this_is_a_test") == "thisIsATest"

    def test_empty_string(self):
        assert to_camel_case("") == ""

    def test_leading_underscore(self):
        assert to_camel_case("_leading_underscore") == "LeadingUnderscore"

    def test_trailing_underscore(self):
        assert to_camel_case("trailing_underscore_") == "trailingUnderscore"

    def test_multiple_consecutive_underscores(self):
        assert to_camel_case("multiple__underscores") == "multipleUnderscores"

    def test_all_uppercase(self):
        assert to_camel_case("ALL_UPPERCASE") == "allUppercase"

    def test_mixed_case(self):
        assert to_camel_case("Mixed_Case_String") == "mixedCaseString"


class TestToSnakeCase:
    def test_single_word(self):
        assert to_snake_case("word") == "word"

    def test_two_words(self):
        assert to_snake_case("exampleString") == "example_string"

    def test_multiple_words(self):
        assert to_snake_case("thisIsATest") == "this_is_a_test"

    def test_empty_string(self):
        assert to_snake_case("") == ""

    def test_leading_uppercase(self):
        assert to_snake_case("LeadingUppercase") == "leading_uppercase"

    def test_trailing_uppercase(self):
        assert to_snake_case("trailingUppercase") == "trailing_uppercase"

    def test_consecutive_uppercase(self):
        assert to_snake_case("HTTPResponseCode") == "http_response_code"

    def test_all_uppercase(self):
        assert to_snake_case("ALLUPPERCASE") == "alluppercase"

    def test_mixed_case(self):
        assert to_snake_case("MixedCaseString") == "mixed_case_string"
