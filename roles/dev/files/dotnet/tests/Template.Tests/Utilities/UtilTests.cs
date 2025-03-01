namespace Template.Tests;

using Template.Utilities;

public class UtilTests
{
    [TestCase("One", "Two")]
    public void JoinStrings_Concatenates_With_Comma_And_Space(string a, string b)
    {
        Assert.That(Util.JoinStrings(new[] { a, b }), Is.EqualTo($"{a}, {b}"));
    }
}
