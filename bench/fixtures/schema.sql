-- Fixture database for `bench`. Built by code at test time into a temp directory, so
-- the repo carries TEXT, not a sqlite binary blob.
--
-- Shaped like a small BIRD database on purpose: a couple of related tables, a nullable
-- numeric column, duplicate rows reachable by a join, and enough rows that an aggregate
-- is not the same number as a count. The fixture tasks in `dev.json` cover one task per
-- structural family so the shape extractor, the selector and the scorer are all
-- exercised offline.

CREATE TABLE county (
    county_id   INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    region      TEXT NOT NULL
);

CREATE TABLE school (
    school_id   INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    county_id   INTEGER NOT NULL REFERENCES county(county_id),
    enrollment  INTEGER,
    free_meals  INTEGER,
    charter     INTEGER NOT NULL
);

INSERT INTO county (county_id, name, region) VALUES
    (1, 'Alameda',   'Bay Area'),
    (2, 'Fresno',    'Central Valley'),
    (3, 'San Mateo', 'Bay Area'),
    (4, 'Modoc',     'Northern');

-- Modoc deliberately has no schools: it makes LEFT JOIN differ from INNER JOIN, so a
-- scorer bug that ignores join type cannot pass unnoticed.
INSERT INTO school (school_id, name, county_id, enrollment, free_meals, charter) VALUES
    (1,  'Oak Ridge High',    1, 1200, 600,  0),
    (2,  'Bayview Charter',   1,  450, 315,  1),
    (3,  'Hillside Academy',  1,  800, 160,  1),
    (4,  'Valley Central',    2, 2100, 1680, 0),
    (5,  'Fresno Tech',       2,  950, 475,  1),
    (6,  'Orchard Elementary',2,  300, 270,  0),
    (7,  'Peninsula Prep',    3,  600, 60,   1),
    (8,  'Coastline High',    3, 1500, 450,  0),
    (9,  'Marsh Creek',       3,  220, NULL, 0),
    (10, 'Summit Charter',    1,  380, 342,  1);
