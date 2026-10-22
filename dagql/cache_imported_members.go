package dagql

// setResultImportedLocked updates a value's origin and the counts of its
// current output classes. Unregistered values acquire their memberships later.
// Requires egraphMu for writing, like the imported field itself.
func (c *Cache) setResultImportedLocked(row *sharedResult, imported bool) {
	if row.imported == imported {
		return
	}
	row.imported = imported
	if c.resultsByID[row.id] != row {
		return
	}
	delta := -1
	if imported {
		delta = 1
	}
	for class := range c.resultOutputEqClasses[row.id] {
		c.adjustImportedMemberCountLocked(class, delta)
	}
}

func (c *Cache) adjustImportedMemberCountLocked(class eqClassID, delta int) {
	count := c.outputEqClassImported[class] + delta
	if count == 0 {
		delete(c.outputEqClassImported, class)
		return
	}
	if c.outputEqClassImported == nil {
		c.outputEqClassImported = make(map[eqClassID]int)
	}
	c.outputEqClassImported[class] = count
}
