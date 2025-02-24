import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import com.example.util.Util;

class UtilTests {
    @ParameterizedTest
    @CsvSource({
        "One, Two"
    })
    void joinStrings_concatenates_with_comma_and_space(
        final String a,
        final String b
    ) {
        assertEquals(String.format("%s, %s", a, b), Util.joinStrings(a, b));
    }
}
