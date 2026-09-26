/**
 * Sector slugs from the backend, rendered as readable labels.
 *
 * One map for every screen. It was previously copied into three pages, and
 * all three copies missed the sectors added when the ingest filters were
 * relaxed, so those records showed raw slugs. Keep this in step with
 * SECTOR_RULES in data/ingest_archive.py.
 */
export const SECTOR_LABEL = {
  electrical_cables: 'Electrical cables',
  electrical_installations: 'Electrical installations',
  cement_building_materials: 'Cement & building materials',
  steel_pipes_fittings: 'Steel pipes & fittings',
  structural_steel: 'Structural steel',
  plastic_pipes: 'Plastic pipes',
  ppe: 'Personal protective equipment',
  geotechnical: 'Geotechnical & soils',
  water_quality: 'Water & sanitation',
  textiles: 'Textiles & apparel',
  timber_furniture: 'Timber & furniture',
  machinery_equipment: 'Machinery & equipment',
  chemicals: 'Chemicals',
  food_agriculture: 'Food & agriculture',
  packaging: 'Packaging',
  rubber_leather: 'Rubber & leather',
  measurement_testing: 'Measurement & test methods',
  electronics_telecom: 'Electronics & telecom',
  metals_alloys: 'Metals & alloys',
  paints_coatings: 'Paints & coatings',
  petroleum_lubricants: 'Petroleum & lubricants',
  refractories_ceramics: 'Refractories & ceramics',
  mechanical_fittings: 'Mechanical fittings',
  paper_printing: 'Paper & printing',
  automotive: 'Automotive',
  medical_laboratory: 'Medical & laboratory',
  // No sector rule matched. Stated plainly rather than guessed.
  general: 'General (unclassified)',
};

export const sectorLabel = (slug, fallback = '') =>
  SECTOR_LABEL[slug] ?? (slug || fallback).replace(/_/g, ' ');
