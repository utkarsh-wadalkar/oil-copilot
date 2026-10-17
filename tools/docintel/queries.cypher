// Starter queries for the Document Intelligence graph produced by tools/docintel/ingest.py
// Paste into Neo4j Browser, Bloom search, or Aura's Query tab.

// 1. What the pipeline produced, by label
MATCH (n) RETURN labels(n)[0] AS label, count(*) AS nodes ORDER BY nodes DESC;

// 2. Relationship types across the whole graph
MATCH ()-[r]->() RETURN type(r) AS relationship, count(*) AS c ORDER BY c DESC;

// 3. A well's full document trail
MATCH (w:Well {id: 'WELL-0001'})-[:HAS_DOCUMENT]->(d:Document)
RETURN w.id, d.kind, d.title, d.chunk_count
ORDER BY d.kind, d.title;

// 4. Which procedures and regulations a well's reports cite
MATCH (w:Well {id: 'WELL-0001'})-[:HAS_DOCUMENT]->(:Document)
      -[:HAS_CHUNK]->(:Chunk)-[:MENTIONS]->(e)
WHERE e:Protocol OR e:Regulation
RETURN DISTINCT labels(e)[0] AS type, e.id AS cited, count(*) AS mentions
ORDER BY mentions DESC;

// 5. The people and equipment involved with a well
MATCH (w:Well {id: 'WELL-0001'})
OPTIONAL MATCH (w)-[:HAS_EQUIPMENT]->(eq:Equipment)
OPTIONAL MATCH (w)-[:ASSIGNED_TO]->(p:Person)
RETURN w.id, collect(DISTINCT eq.name) AS equipment, collect(DISTINCT p.name) AS in_charge;

// 6. Protocol -> what it applies to (extracted relations)
MATCH (p:Protocol)-[r]->(e)
RETURN p.id AS protocol, type(r) AS relation, labels(e)[0] AS target_type, e.name AS target
ORDER BY protocol, relation LIMIT 100;

// 7. Documents that mention spills, with their chunks
MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)-[:MENTIONS]->(s:Spill)
RETURN d.title, d.kind, c.index, s.name
ORDER BY d.title, c.index LIMIT 50;

// 8. Well type coverage and the manuals that describe them
MATCH (w:Well)-[:OF_TYPE]->(t:WellType)
OPTIONAL MATCH (d:Document)-[:DESCRIBES]->(t)
RETURN t.id AS well_type, count(DISTINCT w) AS wells, collect(DISTINCT d.title) AS manuals
ORDER BY wells DESC;

// 9. Areas, their teams, and well counts
MATCH (a:Area)<-[:MANAGES]-(t:Team)
OPTIONAL MATCH (w:Well)-[:LOCATED_IN]->(a)
RETURN a.id AS area, a.name, t.id AS team, count(DISTINCT w) AS wells
ORDER BY wells DESC;

// 10. Chunk-level evidence for a keyword
MATCH (c:Chunk) WHERE toLower(c.text) CONTAINS 'reportable'
RETURN c.document_id, c.index, left(c.text, 400) AS excerpt LIMIT 10;
