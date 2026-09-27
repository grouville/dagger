package dagger

import "context"

// XXX_ItemsJSON is an internal CLI projection of the artifact selection.
// It appends the hidden JSON leaf without first materializing the selection ID.
// A nil dimension expands all items; a non-nil value, including an empty string,
// preserves the explicit dimension argument. This is not a public module API.
func (r *Artifacts) XXX_ItemsJSON(ctx context.Context, absolute, typeAssertion bool, dimension *string) (string, error) {
	q := r.query.SelectWithAlias("items", "__itemsJSON").
		Arg("absolute", absolute).
		Arg("typeAssertion", typeAssertion)
	if dimension != nil {
		q = q.Arg("dimension", *dimension)
	}
	var response string
	err := q.Bind(&response).Execute(ctx)
	return response, err
}
