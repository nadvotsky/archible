package util_test

import (
	"testing"
	"github.com/stretchr/testify/assert"
	"example.com/go-template/util"
)

func TestJoinStringsSeparator(t *testing.T) {
	assert.Equal(t, "One, Two", util.JoinStrings("One", "Two"))
}
