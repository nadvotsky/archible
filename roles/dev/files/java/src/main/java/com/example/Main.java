package com.example;

import com.example.util.Util;

public final class Main {
    protected Main() {
        throw new UnsupportedOperationException();
    }

    public static void main(final String[] args) {
        System.out.println(Util.joinStrings("Hello", "World!"));
    }
}
