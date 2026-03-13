package dagql

import (
	"errors"
	"fmt"
	"strings"
)

type PanicError struct {
	Cause     any
	Self      AnyResult
	Selection Selection
	Stack     []byte
}

func (err PanicError) Error() string {
	return fmt.Sprintf("panic while resolving %s.%s: %v\n\n%s",
		err.Self.Type().Name(),
		err.Selection.Alias,
		err.Cause,
		string(err.Stack))
}

func IsUnavailableFieldError(err error, typeName, fieldName string) bool {
	if err == nil {
		return false
	}

	msg := err.Error()
	if !strings.Contains(msg, "Cannot query field") ||
		!strings.Contains(msg, fieldName) ||
		!strings.Contains(msg, typeName) {
		return false
	}

	var extErr interface {
		error
		Extensions() map[string]any
	}
	if errors.As(err, &extErr) {
		code, _ := extErr.Extensions()["code"].(string)
		return code == "" || code == "GRAPHQL_VALIDATION_FAILED"
	}
	return true
}
