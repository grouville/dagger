package dagql

import (
	"errors"
	"testing"

	"github.com/stretchr/testify/require"
)

type testExtendedError struct {
	msg  string
	exts map[string]any
}

func (e testExtendedError) Error() string {
	return e.msg
}

func (e testExtendedError) Extensions() map[string]any {
	return e.exts
}

func TestIsUnavailableFieldError(t *testing.T) {
	t.Run("graphql validation extensions", func(t *testing.T) {
		err := testExtendedError{
			msg:  `Cannot query field "diffStat" on type "Changeset"`,
			exts: map[string]any{"code": "GRAPHQL_VALIDATION_FAILED"},
		}
		require.True(t, IsUnavailableFieldError(err, "Changeset", "diffStat"))
	})

	t.Run("graphql validation different field", func(t *testing.T) {
		err := testExtendedError{
			msg:  `Cannot query field "bar" on type "Changeset"`,
			exts: map[string]any{"code": "GRAPHQL_VALIDATION_FAILED"},
		}
		require.False(t, IsUnavailableFieldError(err, "Changeset", "diffStat"))
	})

	t.Run("wrapped field unavailable message", func(t *testing.T) {
		err := errors.New(`server response: Cannot query field "diffStat" on type "Changeset"`)
		require.True(t, IsUnavailableFieldError(err, "Changeset", "diffStat"))
	})

	t.Run("different field", func(t *testing.T) {
		err := errors.New(`Cannot query field "bar" on type "Changeset"`)
		require.False(t, IsUnavailableFieldError(err, "Changeset", "diffStat"))
	})
}
