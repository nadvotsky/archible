package util

import (
	"strings"
)

func JoinStrings(parts ...string) string {
	return strings.Join(parts, ", ")
}
