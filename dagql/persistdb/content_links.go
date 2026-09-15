package persistdb

import "context"

type MirrorResultContentLink struct {
	ResultID int64
	Digest   string
	Role     string
}

const clearMirrorResultContentLinks = `DELETE FROM result_content_links`

func (q *Queries) InsertMirrorResultContentLink(ctx context.Context, arg MirrorResultContentLink) error {
	_, err := q.exec(ctx, nil, `INSERT INTO result_content_links (result_id, digest, role) VALUES (?, ?, ?)`, arg.ResultID, arg.Digest, arg.Role)
	return err
}

func (q *Queries) ListMirrorResultContentLinks(ctx context.Context) ([]MirrorResultContentLink, error) {
	rows, err := q.db.QueryContext(ctx, `SELECT result_id, digest, role FROM result_content_links`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var links []MirrorResultContentLink
	for rows.Next() {
		var link MirrorResultContentLink
		if err := rows.Scan(&link.ResultID, &link.Digest, &link.Role); err != nil {
			return nil, err
		}
		links = append(links, link)
	}
	return links, rows.Err()
}
