package com.example.util;

public final class Util {
    protected Util() {
        throw new UnsupportedOperationException();
    }

    public static String joinStrings(final String... strings) {
        return String.join(", ", strings);
    }
}
