# Generator scenarios

The synthetic dataset generator is now driven by YAML scenarios. The old `--preset` interface still works, but new dataset variants should start from a scenario file instead of editing Python constants.

## Built-in scenarios

```text
configs/generation/medium.yaml
configs/generation/behavioral_large.yaml
configs/generation/research_large_high.yaml
configs/generation/research_large_medium.yaml
configs/generation/research_large_sparse_hotspots.yaml
```

Run one directly:

```powershell
python -m src.data_generation.generate_synthetic_mvp `
  --scenario configs/generation/research_large_high.yaml
```

Legacy preset commands are compatibility wrappers:

```powershell
python -m src.data_generation.generate_synthetic_mvp `
  --preset research_large `
  --competition-profile high
```

Both forms keep the same CSV schema.

## Scenario fields

```yaml
name: research_large_high
version: 1
output_dir: data/synthetic/research_large
competition_profile: high
shape:
  preset: research_large
  n_students: 800
  n_course_sections: 240
  n_profiles: 6
  n_course_codes: 154
catalog:
  category_counts:
    Foundation: 24
    MajorCore: 42
    MajorElective: 44
    GeneralElective: 26
    English: 6
    PE: 6
    LabSeminar: 6
eligibility:
  eligible_bounds: [120, 185]
policies:
  catalog: course_catalog_v1
  requirements: profile_requirements_v1
  capacity: research_large_high_capacity_v1
  eligibility: broad_admin_eligibility_v1
  utility: profile_affinity_utility_v1
```

The policy names are explicit markers for the current generator behavior. They are intentionally not arbitrary expressions; v1 scenarios only allow enumerated policies and numeric parameters.

## Allowed CLI overrides

```powershell
python -m src.data_generation.generate_synthetic_mvp `
  --scenario configs/generation/research_large_high.yaml `
  --n-students 600 `
  --n-course-sections 200 `
  --n-profiles 6 `
  --n-course-codes 140 `
  --output-dir data/synthetic/custom_research_600
```

When `n_profiles` or `n_course_codes` is overridden, category counts are recomputed by the default catalog policy. When `n_course_sections` is overridden, eligible bounds are recomputed from the section count.

## Validation rules

- `n_profiles` must be `3-6`.
- `n_students`, `n_course_sections`, and `n_course_codes` must be positive.
- `n_course_codes` must not exceed `n_course_sections`.
- `n_course_codes` must be large enough for common required courses and profile-specific required courses.
- `category_counts` must sum to `n_course_codes`.
- Foundation, English, and MajorCore must be sufficient for the required-course policy.
- `eligible_bounds` must satisfy `0 <= min <= max <= n_course_sections`.
- `competition_profile` must be `high`, `medium`, `sparse_hotspots`, or future explicit `custom`.

## Metadata

Generated `generation_metadata.json` now includes:

- `scenario_name`
- `scenario_path`
- `scenario_version`
- `effective_parameters`

This makes reports traceable to the exact scenario and overrides used to create the data.
