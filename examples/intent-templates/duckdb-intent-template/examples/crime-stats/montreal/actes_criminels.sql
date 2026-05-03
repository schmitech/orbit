CREATE TABLE IF NOT EXISTS actes_criminels (
    id INTEGER PRIMARY KEY,
    categorie VARCHAR,
    date_evenement DATE,
    quart VARCHAR,
    pdq INTEGER,
    x DOUBLE,
    y DOUBLE,
    longitude DOUBLE,
    latitude DOUBLE,
    arrondissement VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_actes_criminels_categorie ON actes_criminels(categorie);
CREATE INDEX IF NOT EXISTS idx_actes_criminels_date ON actes_criminels(date_evenement);
CREATE INDEX IF NOT EXISTS idx_actes_criminels_quart ON actes_criminels(quart);
CREATE INDEX IF NOT EXISTS idx_actes_criminels_pdq ON actes_criminels(pdq);
CREATE INDEX IF NOT EXISTS idx_actes_criminels_arrondissement ON actes_criminels(arrondissement);
