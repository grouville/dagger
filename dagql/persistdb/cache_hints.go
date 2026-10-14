package persistdb

import "context"

type MirrorCacheHint struct {
	Key      string
	ResultID int64
	Position int64
}

func (q *Queries) InsertMirrorCacheHint(ctx context.Context, row MirrorCacheHint) error {
	_, err := q.exec(ctx, nil, `INSERT INTO cache_hints (key, result_id, position) VALUES (?, ?, ?)`, row.Key, row.ResultID, row.Position)
	return err
}

func (q *Queries) ListMirrorCacheHints(ctx context.Context) ([]MirrorCacheHint, error) {
	rows, err := q.db.QueryContext(ctx, `SELECT key, result_id, position FROM cache_hints ORDER BY position`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var hints []MirrorCacheHint
	for rows.Next() {
		var hint MirrorCacheHint
		if err := rows.Scan(&hint.Key, &hint.ResultID, &hint.Position); err != nil {
			return nil, err
		}
		hints = append(hints, hint)
	}
	return hints, rows.Err()
}
