from __future__ import annotations

import filecmp
import tempfile
import unittest
from pathlib import Path

from src.data_generation.generate_synthetic_mvp import (
    TIME_BLOCKS,
    WEEKDAYS,
    build_custom_dataset,
    build_medium_dataset,
    build_synthetic_dataset,
    default_output_dir_for_preset,
    build_shape,
    write_dataset,
)
from src.data_generation.audit_synthetic_dataset import audit_rows
from src.data_generation.io import (
    load_courses,
    load_requirements,
    load_students,
    load_utility_edges,
    resolve_data_paths,
    validate_dataset,
)
from src.student_agents.context import derive_requirement_penalties


class MediumDatasetGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = build_medium_dataset(20260425)

    def test_medium_scale_matches_spec(self) -> None:
        profiles = self.dataset["profiles"]
        students = self.dataset["students"]
        courses = self.dataset["courses"]
        course_codes = {course["course_code"] for course in courses}
        self.assertGreaterEqual(len(profiles), 3)
        self.assertLessEqual(len(profiles), 5)
        self.assertEqual(len(students), 100)
        self.assertEqual(len(courses), 80)
        self.assertGreaterEqual(len(course_codes), 45)
        self.assertLessEqual(len(course_codes), 55)

    def test_profiles_and_profile_requirements_are_consistent(self) -> None:
        profiles = self.dataset["profiles"]
        profile_requirements = self.dataset["profile_requirements"]
        students = self.dataset["students"]
        profile_ids = {profile["profile_id"] for profile in profiles}
        self.assertEqual(len(profile_ids), len(profiles))
        self.assertTrue(all(student["profile_id"] in profile_ids for student in students))
        self.assertTrue(all(requirement["profile_id"] in profile_ids for requirement in profile_requirements))

        required_by_profile: dict[str, set[str]] = {profile_id: set() for profile_id in profile_ids}
        requirement_counts: dict[str, dict[str, int]] = {profile_id: {} for profile_id in profile_ids}
        optional_by_profile: dict[str, set[str]] = {profile_id: set() for profile_id in profile_ids}
        courses_by_code = {course["course_code"]: course for course in self.dataset["courses"]}
        for requirement in profile_requirements:
            profile_id = requirement["profile_id"]
            requirement_type = requirement["requirement_type"]
            requirement_counts[profile_id][requirement_type] = requirement_counts[profile_id].get(requirement_type, 0) + 1
            if requirement["requirement_type"] == "required":
                required_by_profile[requirement["profile_id"]].add(requirement["course_code"])
            if requirement["requirement_type"] == "optional_target":
                optional_by_profile[profile_id].add(requirement["course_code"])
        self.assertTrue(all(len(required_codes) == 7 for required_codes in required_by_profile.values()))
        self.assertTrue(all(counts.get("optional_target") == 4 for counts in requirement_counts.values()))
        self.assertTrue(
            all(
                any(courses_by_code[course_code]["category"] == "LabSeminar" for course_code in optional_codes)
                for optional_codes in optional_by_profile.values()
            )
        )
        self.assertGreater(len({tuple(sorted(required_codes)) for required_codes in required_by_profile.values()}), 1)
        common_required = set.intersection(*required_by_profile.values())
        self.assertLessEqual(len(common_required), 4)
        self.assertEqual(common_required, {"FND001", "ENG001", "MCO001"})

    def test_student_requirements_are_derived_from_profiles(self) -> None:
        profile_lookup = {
            (
                requirement["profile_id"],
                requirement["course_code"],
                requirement["requirement_type"],
                requirement["deadline_term"],
            )
            for requirement in self.dataset["profile_requirements"]
        }
        profile_by_student = {student["student_id"]: student["profile_id"] for student in self.dataset["students"]}
        for requirement in self.dataset["requirements"]:
            key = (
                profile_by_student[requirement["student_id"]],
                requirement["course_code"],
                requirement["requirement_type"],
                requirement["deadline_term"],
            )
            self.assertIn(key, profile_lookup)

    def test_required_deadlines_and_student_pressure_are_grade_layered(self) -> None:
        required_deadlines = {
            requirement["deadline_term"]
            for requirement in self.dataset["profile_requirements"]
            if requirement["requirement_type"] == "required"
        }
        self.assertGreaterEqual(len(required_deadlines), 4)
        self.assertNotEqual(required_deadlines, {"current"})

        high_pressure_by_student: dict[str, list[str]] = {}
        courses_by_code: dict[str, list[dict]] = {}
        for course in self.dataset["courses"]:
            courses_by_code.setdefault(course["course_code"], []).append(course)
        for requirement in self.dataset["requirements"]:
            if requirement["requirement_type"] == "required" and requirement["requirement_priority"] in {
                "degree_blocking",
                "progress_blocking",
            }:
                high_pressure_by_student.setdefault(requirement["student_id"], []).append(requirement["course_code"])

        for student in self.dataset["students"]:
            high_pressure_codes = high_pressure_by_student.get(student["student_id"], [])
            self.assertGreaterEqual(len(high_pressure_codes), 3)
            self.assertLessEqual(len(high_pressure_codes), 4)
            min_credits = sum(min(float(section["credit"]) for section in courses_by_code[code]) for code in high_pressure_codes)
            self.assertLessEqual(min_credits, 20.0)

    def test_credits_are_half_point_values_in_range(self) -> None:
        for course in self.dataset["courses"]:
            credit = float(course["credit"])
            self.assertGreaterEqual(credit, 0.5)
            self.assertLessEqual(credit, 7.0)
            self.assertEqual(credit * 2, int(credit * 2))

    def test_time_slots_are_atomic_and_lunch_is_sparse(self) -> None:
        session_blocks: list[str] = []
        for course in self.dataset["courses"]:
            for fragment in str(course["time_slot"]).split("|"):
                parts = fragment.split("-")
                self.assertEqual(len(parts), 3)
                day = parts[0]
                block = f"{parts[1]}-{parts[2]}"
                self.assertIn(day, WEEKDAYS)
                self.assertIn(block, TIME_BLOCKS)
                self.assertNotIn(block, {"1-4", "3-6", "7-10"})
                session_blocks.append(block)
        lunch_share = session_blocks.count("5-6") / len(session_blocks)
        self.assertLessEqual(lunch_share, 0.03)
        self.assertTrue(session_blocks.count("11-12") >= 5 or session_blocks.count("11-12") / len(session_blocks) >= 0.02)
        for course in self.dataset["courses"]:
            if course["category"] in {"Foundation", "English", "MajorCore"}:
                self.assertNotIn("5-6", str(course["time_slot"]))

    def test_medium_uses_broad_but_not_universal_eligibility(self) -> None:
        courses_by_id = {course["course_id"]: course for course in self.dataset["courses"]}
        eligible_by_student: dict[str, set[str]] = {}
        ineligible_count = 0
        for edge in self.dataset["utilities"]:
            self.assertIn(edge["eligible"], {"true", "false"})
            if edge["eligible"] == "true":
                eligible_by_student.setdefault(edge["student_id"], set()).add(edge["course_id"])
            else:
                ineligible_count += 1
        self.assertEqual(len(self.dataset["utilities"]), len(self.dataset["students"]) * len(self.dataset["courses"]))
        self.assertGreater(ineligible_count, 0)
        for student in self.dataset["students"]:
            count = len(eligible_by_student[student["student_id"]])
            self.assertGreaterEqual(count, 45)
            self.assertLessEqual(count, 70)

        for requirement in self.dataset["requirements"]:
            student_id = requirement["student_id"]
            course_code = requirement["course_code"]
            eligible_codes = {
                courses_by_id[course_id]["course_code"]
                for course_id in eligible_by_student[student_id]
            }
            self.assertIn(course_code, eligible_codes)

        cross_category_counts = []
        for student in self.dataset["students"]:
            student_id = student["student_id"]
            eligible_categories = {
                courses_by_id[course_id]["category"]
                for course_id in eligible_by_student[student_id]
            }
            cross_category_counts.append(len(eligible_categories))
        self.assertTrue(all(count >= 5 for count in cross_category_counts))

    def test_utility_edges_are_scalar_only(self) -> None:
        expected_fields = {"student_id", "course_id", "eligible", "utility"}
        for edge in self.dataset["utilities"]:
            self.assertEqual(set(edge), expected_fields)
            self.assertGreaterEqual(float(edge["utility"]), 1)
            self.assertLessEqual(float(edge["utility"]), 100)

    def test_same_seed_outputs_identical_csv_files(self) -> None:
        first = build_medium_dataset(20260425)
        second = build_medium_dataset(20260425)
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first_root = Path(first_dir)
            second_root = Path(second_dir)
            write_dataset(first, first_root)
            write_dataset(second, second_root)
            for filename in [
                "profiles.csv",
                "profile_requirements.csv",
                "students.csv",
                "courses.csv",
                "student_course_code_requirements.csv",
                "student_course_utility_edges.csv",
                "generation_metadata.json",
            ]:
                self.assertTrue(filecmp.cmp(first_root / filename, second_root / filename, shallow=False), filename)

    def test_generated_csv_loads_with_existing_io(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_dataset(self.dataset, root)
            self.assertTrue((root / "profiles.csv").exists())
            self.assertTrue((root / "profile_requirements.csv").exists())
            students = load_students(root / "students.csv")
            courses = load_courses(root / "courses.csv")
            edges = load_utility_edges(root / "student_course_utility_edges.csv")
            requirements = load_requirements(root / "student_course_code_requirements.csv")
            validate_dataset(students, courses, edges, requirements)
            self.assertEqual(len(students), 100)
            self.assertEqual(len(courses), 80)
            penalties = derive_requirement_penalties(students, edges, requirements)
            pressures = []
            for student_id in students:
                pressures.append(sum(penalties.get((student_id, requirement.course_code), 0.0) for requirement in requirements if requirement.student_id == student_id))
            self.assertGreater(len({round(value, 4) for value in pressures}), 1)

    def test_audit_rows_passes_medium_dataset(self) -> None:
        result = audit_rows(
            self.dataset["students"],
            self.dataset["profiles"],
            self.dataset["profile_requirements"],
            self.dataset["courses"],
            self.dataset["requirements"],
            self.dataset["utilities"],
        )
        self.assertTrue(result["passed"], result["errors"])
        self.assertLessEqual(result["summary"]["time"]["lunch_share"], 0.03)
        pressure = result["summary"]["competition_pressure"]
        self.assertGreaterEqual(pressure["predicted_overloaded_section_count"], 8)
        self.assertGreaterEqual(
            pressure["predicted_overloaded_section_count"] + pressure["predicted_near_full_section_count"],
            12,
        )
        self.assertGreaterEqual(pressure["high_pressure_required_overloaded_section_count"], 3)
        self.assertGreaterEqual(pressure["predicted_admission_rate_proxy"], 0.75)
        self.assertLessEqual(pressure["predicted_admission_rate_proxy"], 0.92)
        demand_share = pressure["predicted_demand_share_by_category"]
        self.assertLessEqual(demand_share.get("Foundation", 0.0), 0.60)
        self.assertGreaterEqual(demand_share.get("GeneralElective", 0.0), 0.08)
        self.assertGreaterEqual(demand_share.get("PE", 0.0), 0.03)
        self.assertGreaterEqual(demand_share.get("LabSeminar", 0.0), 0.01)
        self.assertLessEqual(demand_share.get("LabSeminar", 0.0), 0.13)
        self.assertGreaterEqual(
            demand_share.get("MajorCore", 0.0) + demand_share.get("MajorElective", 0.0),
            0.25,
        )
        self.assertIn("MajorCore", pressure["top_overloaded_sections_by_category"])
        self.assertLessEqual(result["summary"]["requirements"]["profile_required_overlap"]["common_required_count"], 4)
        for credits in result["summary"]["requirements"]["profile_required_credit"].values():
            self.assertGreaterEqual(credits, 20)
            self.assertLessEqual(credits, 27)
            self.assertLess(credits, 30)

    def test_student_source_can_be_configured_for_custom_output_dir(self) -> None:
        paths = resolve_data_paths(
            {
                "objective": {
                    "profile_source": "custom/profiles.csv",
                    "profile_requirements_source": "custom/profile_requirements.csv",
                    "student_source": "custom/students.csv",
                    "course_metadata_source": "custom/courses.csv",
                    "utility_source": "custom/student_course_utility_edges.csv",
                    "requirements_source": "custom/student_course_code_requirements.csv",
                }
            }
        )
        self.assertEqual(paths["profiles"], Path("custom/profiles.csv"))
        self.assertEqual(paths["profile_requirements"], Path("custom/profile_requirements.csv"))
        self.assertEqual(paths["students"], Path("custom/students.csv"))

    def test_custom_small_dataset_matches_requested_shape(self) -> None:
        dataset = build_custom_dataset(42, n_students=10, n_course_sections=20, n_profiles=3)
        self.assertEqual(len(dataset["profiles"]), 3)
        self.assertEqual(len(dataset["students"]), 10)
        self.assertEqual(len(dataset["courses"]), 20)
        self.assertEqual(len(dataset["utilities"]), 200)
        self.assertTrue(all(edge["eligible"] == "true" for edge in dataset["utilities"]))
        profile_ids = {profile["profile_id"] for profile in dataset["profiles"]}
        self.assertTrue(all(student["profile_id"] in profile_ids for student in dataset["students"]))
        self.assertEqual(dataset["metadata"]["preset"], "custom")
        self.assertEqual(dataset["metadata"]["n_students"], 10)
        self.assertEqual(dataset["metadata"]["n_course_sections"], 20)
        self.assertEqual(dataset["metadata"]["profile_count"], 3)
        self.assertIn("profile_required_deadline_summary", dataset["metadata"])

    def test_custom_default_output_dir_uses_scale_and_seed(self) -> None:
        shape = build_shape("custom", n_students=10, n_course_sections=20, n_profiles=3)
        self.assertEqual(
            default_output_dir_for_preset("custom", 42, shape),
            Path("data/synthetic/n10_c20_p3_seed42"),
        )
        self.assertEqual(
            default_output_dir_for_preset("behavioral_large", 20260427, build_shape("behavioral_large")),
            Path("data/synthetic/behavioral_large"),
        )

    def test_behavioral_large_shape_and_audit(self) -> None:
        for seed in (20260427, 42):
            dataset = build_synthetic_dataset(seed, build_shape("behavioral_large"))
            self.assertEqual(len(dataset["students"]), 300)
            self.assertEqual(len(dataset["courses"]), 120)
            self.assertEqual(len(dataset["utilities"]), 36000)
            self.assertEqual(dataset["metadata"]["preset"], "behavioral_large")
            result = audit_rows(
                dataset["students"],
                dataset["profiles"],
                dataset["profile_requirements"],
                dataset["courses"],
                dataset["requirements"],
                dataset["utilities"],
            )
            self.assertTrue(result["passed"], result["errors"])
            pressure = result["summary"]["competition_pressure"]
            self.assertGreaterEqual(pressure["predicted_overloaded_section_count"], 14)
            self.assertGreaterEqual(
                pressure["predicted_overloaded_section_count"] + pressure["predicted_near_full_section_count"],
                20,
            )
            self.assertGreaterEqual(pressure["predicted_admission_rate_proxy"], 0.65)
            self.assertLessEqual(pressure["predicted_admission_rate_proxy"], 0.88)
            demand_share = pressure["predicted_demand_share_by_category"]
            self.assertLessEqual(demand_share.get("Foundation", 0.0), 0.55)
            self.assertGreaterEqual(
                demand_share.get("MajorCore", 0.0) + demand_share.get("MajorElective", 0.0),
                0.35,
            )
            self.assertGreater(demand_share.get("PE", 0.0), 0.0)
            self.assertGreater(demand_share.get("LabSeminar", 0.0), 0.0)

    def test_custom_dataset_seed_behavior(self) -> None:
        first = build_custom_dataset(42, n_students=10, n_course_sections=20, n_profiles=3)
        second = build_custom_dataset(42, n_students=10, n_course_sections=20, n_profiles=3)
        third = build_custom_dataset(43, n_students=10, n_course_sections=20, n_profiles=3)
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first_root = Path(first_dir)
            second_root = Path(second_dir)
            write_dataset(first, first_root)
            write_dataset(second, second_root)
            for filename in [
                "profiles.csv",
                "profile_requirements.csv",
                "students.csv",
                "courses.csv",
                "student_course_code_requirements.csv",
                "student_course_utility_edges.csv",
                "generation_metadata.json",
            ]:
                self.assertTrue(
                    filecmp.cmp(first_root / filename, second_root / filename, shallow=False),
                    filename,
                )
        self.assertNotEqual(first["metadata"]["effective_seed"], third["metadata"]["effective_seed"])
        self.assertNotEqual(first["utilities"], third["utilities"])


if __name__ == "__main__":
    unittest.main()
