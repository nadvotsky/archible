pub fn join_strings<S>(strings: &[S]) -> String
where
    S: AsRef<str>,
{
    strings
        .iter()
        .map(|s| s.as_ref())
        .collect::<Vec<&str>>()
        .join(", ")
}

#[cfg(test)]
mod tests {
    use super::*;

    //
    // GIVEN-WHEN-THEN or SHOULD-WHEN
    //

    #[test]
    fn join_strings_accepts_slice() {
        assert_eq!(join_strings(&["One", "Two"]), "One, Two");
    }

    #[test]
    fn join_strings_accept_vector() {
        assert_eq!(join_strings(&vec!["One", "Two"]), "One, Two");
    }
}