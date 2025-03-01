namespace Template;

using System;
using Template.Utilities;

internal static class Program
{
    private static void Main(string[] args)
    {
        Console.WriteLine(Util.JoinStrings(["Hello", "World"]));
    }
}
