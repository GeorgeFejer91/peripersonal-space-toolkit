"""Tkinter stimulus designer for custom PPS looming designs."""

from __future__ import annotations

import argparse
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .design import (
    NoiseDefinition,
    ProtocolSpec,
    StimulusDesign,
    TrajectorySpec,
    default_design,
    export_protocol_csv,
    export_trajectory_csv,
    load_design,
    protocol_summary,
    save_design,
    snap_noises_to_sofa,
    sofa_summary,
    trajectory_points,
    validate_design,
)
from .templates import StudyTemplate, load_templates


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DESIGN_PATH = REPO_ROOT / "configs" / "stimulus_design.generated.json"
TEMPLATE_DIR = REPO_ROOT / "study_templates"


class StimulusDesignerApp:
    def __init__(self, root: tk.Tk, design_path: Path = DEFAULT_DESIGN_PATH):
        self.root = root
        self.design_path = design_path
        self.design = load_design(design_path) if design_path.exists() else default_design()
        self.noises: list[NoiseDefinition] = list(self.design.noises)
        self.templates: list[StudyTemplate] = load_templates(TEMPLATE_DIR)

        self.root.title("Peripersonal Space Toolkit - Stimulus Designer")
        self.root.geometry("1120x760")
        self.root.minsize(980, 640)

        self.name_var = tk.StringVar()
        self.sofa_var = tk.StringVar()
        self.noise_label_var = tk.StringVar()
        self.noise_type_var = tk.StringVar()
        self.noise_azimuth_var = tk.StringVar()
        self.noise_elevation_var = tk.StringVar()
        self.noise_gain_var = tk.StringVar()
        self.template_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready.")

        self.traj_vars = {
            "start_radius_m": tk.StringVar(),
            "end_radius_m": tk.StringVar(),
            "path_direction": tk.StringVar(),
            "path_length_m": tk.StringVar(),
            "propagation_speed_mps": tk.StringVar(),
            "azimuth_start_deg": tk.StringVar(),
            "azimuth_end_deg": tk.StringVar(),
            "elevation_deg": tk.StringVar(),
            "padding_pre_s": tk.StringVar(),
            "padding_post_s": tk.StringVar(),
        }
        self.protocol_vars = {
            "repetitions_per_condition": tk.StringVar(),
            "soa_values_ms": tk.StringVar(),
            "spatial_values_cm": tk.StringVar(),
            "auditory_motion_directions": tk.StringVar(),
            "tactile_sites": tk.StringVar(),
            "catch_trial_percentage": tk.StringVar(),
            "catch_trials_exact": tk.StringVar(),
            "baseline_soa_values_ms": tk.StringVar(),
            "respiratory_phases": tk.StringVar(),
            "blocks": tk.StringVar(),
            "participants": tk.StringVar(),
            "random_seed": tk.StringVar(),
        }
        self.pair_spatial_values_var = tk.BooleanVar()
        self.include_baseline_var = tk.BooleanVar()

        self._build_ui()
        self._load_into_fields(self.design)
        self._update_preview()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        header = ttk.LabelFrame(outer, text="Design")
        header.pack(fill="x")
        ttk.Label(header, text="Name").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(header, textvariable=self.name_var, width=32).grid(row=0, column=1, sticky="ew", padx=6, pady=6)
        ttk.Label(header, text="SOFA file").grid(row=0, column=2, sticky="w", padx=6, pady=6)
        ttk.Entry(header, textvariable=self.sofa_var).grid(row=0, column=3, sticky="ew", padx=6, pady=6)
        ttk.Button(header, text="Browse", command=self._browse_sofa).grid(row=0, column=4, padx=4, pady=6)
        ttk.Button(header, text="Validate", command=self._validate_sofa).grid(row=0, column=5, padx=4, pady=6)
        ttk.Label(header, text="Preload").grid(row=1, column=0, sticky="w", padx=6, pady=6)
        template_values = [f"{item.title} [{item.verification_status}]" for item in self.templates]
        self.template_combo = ttk.Combobox(
            header,
            textvariable=self.template_var,
            values=template_values,
            state="readonly",
        )
        self.template_combo.grid(row=1, column=1, columnspan=4, sticky="ew", padx=6, pady=6)
        ttk.Button(header, text="Load Template", command=self._load_template_clicked).grid(row=1, column=5, padx=4, pady=6)
        header.columnconfigure(3, weight=1)

        body = ttk.PanedWindow(outer, orient="horizontal")
        body.pack(fill="both", expand=True, pady=(10, 8))

        left = ttk.Frame(body, padding=(0, 0, 8, 0))
        right = ttk.Frame(body)
        body.add(left, weight=1)
        body.add(right, weight=2)

        self._build_noise_panel(left)
        self._build_protocol_panel(left)
        self._build_trajectory_panel(right)

        footer = ttk.Frame(outer)
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.status_var).pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Load", command=self._load_clicked).pack(side="right", padx=4)
        ttk.Button(footer, text="Save", command=self._save_clicked).pack(side="right", padx=4)
        ttk.Button(footer, text="Export Protocol", command=self._export_protocol_clicked).pack(side="right", padx=4)
        ttk.Button(footer, text="Export Trajectory", command=self._export_trajectory_clicked).pack(side="right", padx=4)
        ttk.Button(footer, text="Check", command=self._check_design).pack(side="right", padx=4)

    def _build_noise_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="Noise Types And Orientations")
        panel.pack(fill="both", expand=True)

        self.noise_tree = ttk.Treeview(
            panel,
            columns=("label", "type", "azimuth", "elevation", "gain"),
            show="headings",
            height=12,
        )
        for column, label, width in [
            ("label", "Label", 140),
            ("type", "Type", 80),
            ("azimuth", "Azimuth", 80),
            ("elevation", "Elevation", 80),
            ("gain", "Gain", 70),
        ]:
            self.noise_tree.heading(column, text=label)
            self.noise_tree.column(column, width=width, anchor="center")
        self.noise_tree.pack(fill="both", expand=True, padx=8, pady=8)
        self.noise_tree.bind("<<TreeviewSelect>>", self._noise_selected)

        form = ttk.Frame(panel)
        form.pack(fill="x", padx=8)
        labels = ["Label", "Type", "Azimuth", "Elevation", "Gain"]
        for idx, text in enumerate(labels):
            ttk.Label(form, text=text).grid(row=0, column=idx, sticky="w", padx=3)

        ttk.Entry(form, textvariable=self.noise_label_var, width=16).grid(row=1, column=0, sticky="ew", padx=3, pady=4)
        ttk.Combobox(
            form,
            textvariable=self.noise_type_var,
            values=("pink", "blue", "white", "brown"),
            width=8,
            state="readonly",
        ).grid(row=1, column=1, padx=3, pady=4)
        ttk.Spinbox(form, textvariable=self.noise_azimuth_var, from_=-180, to=180, increment=1, width=8).grid(row=1, column=2, padx=3, pady=4)
        ttk.Spinbox(form, textvariable=self.noise_elevation_var, from_=-90, to=90, increment=1, width=8).grid(row=1, column=3, padx=3, pady=4)
        ttk.Spinbox(form, textvariable=self.noise_gain_var, from_=0.1, to=2.0, increment=0.1, width=8).grid(row=1, column=4, padx=3, pady=4)
        form.columnconfigure(0, weight=1)

        buttons = ttk.Frame(panel)
        buttons.pack(fill="x", padx=8, pady=(2, 8))
        ttk.Button(buttons, text="Add / Update", command=self._add_or_update_noise).pack(side="left", padx=2)
        ttk.Button(buttons, text="Remove", command=self._remove_noise).pack(side="left", padx=2)
        ttk.Button(buttons, text="Snap To SOFA", command=self._snap_noises).pack(side="left", padx=2)

    def _build_protocol_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="Protocol Schedule")
        panel.pack(fill="both", expand=True, pady=(8, 0))

        form = ttk.Frame(panel)
        form.pack(fill="x", padx=8, pady=8)
        rows = [
            ("repetitions_per_condition", "Repetitions", 0),
            ("soa_values_ms", "SOAs ms", 1),
            ("spatial_values_cm", "Spatial cm", 2),
            ("auditory_motion_directions", "Motions", 3),
            ("tactile_sites", "Tactile sites", 4),
            ("catch_trial_percentage", "Catch %", 5),
            ("catch_trials_exact", "Catch exact", 6),
            ("baseline_soa_values_ms", "Baseline SOAs", 7),
            ("respiratory_phases", "Phases", 8),
            ("blocks", "Blocks", 9),
            ("participants", "Participants", 10),
            ("random_seed", "Seed", 11),
        ]
        for key, label, row in rows:
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=2)
            entry = ttk.Entry(form, textvariable=self.protocol_vars[key], width=22)
            entry.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
            self.protocol_vars[key].trace_add("write", lambda *_: self._update_protocol_summary())
        form.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            form,
            text="Pair SOA and spatial values",
            variable=self.pair_spatial_values_var,
            command=self._update_protocol_summary,
        ).grid(row=12, column=0, columnspan=2, sticky="w", padx=4, pady=2)
        ttk.Checkbutton(
            form,
            text="Include tactile-only baseline",
            variable=self.include_baseline_var,
            command=self._update_protocol_summary,
        ).grid(row=13, column=0, columnspan=2, sticky="w", padx=4, pady=2)

        self.protocol_tree = ttk.Treeview(panel, columns=("metric", "value"), show="headings", height=7)
        self.protocol_tree.heading("metric", text="Metric")
        self.protocol_tree.heading("value", text="Count")
        self.protocol_tree.column("metric", width=150, anchor="w")
        self.protocol_tree.column("value", width=90, anchor="center")
        self.protocol_tree.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _build_trajectory_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="Looming Trajectory")
        panel.pack(fill="both", expand=True)

        controls = ttk.Frame(panel)
        controls.pack(fill="x", padx=8, pady=8)

        rows = [
            ("start_radius_m", "Start radius (m)", 0.01, 10.0, 0.05),
            ("end_radius_m", "End radius (m)", 0.01, 10.0, 0.05),
            ("path_length_m", "Path length (m)", 0.01, 20.0, 0.05),
            ("propagation_speed_mps", "Speed (m/s)", 0.01, 5.0, 0.01),
            ("azimuth_start_deg", "Start azimuth", -180, 180, 1),
            ("azimuth_end_deg", "End azimuth", -180, 180, 1),
            ("elevation_deg", "Elevation", -90, 90, 1),
            ("padding_pre_s", "Lead padding (s)", 0, 5, 0.1),
            ("padding_post_s", "Tail padding (s)", 0, 5, 0.1),
        ]
        for idx, (key, label, lo, hi, step) in enumerate(rows):
            row = idx // 3
            col = (idx % 3) * 2
            ttk.Label(controls, text=label).grid(row=row, column=col, sticky="w", padx=5, pady=4)
            spin = ttk.Spinbox(controls, textvariable=self.traj_vars[key], from_=lo, to=hi, increment=step, width=10, command=self._update_preview)
            spin.grid(row=row, column=col + 1, sticky="w", padx=5, pady=4)
            self.traj_vars[key].trace_add("write", lambda *_: self._update_preview())

        ttk.Label(controls, text="Direction").grid(row=3, column=0, sticky="w", padx=5, pady=4)
        ttk.Combobox(
            controls,
            textvariable=self.traj_vars["path_direction"],
            values=("approach", "recede", "left_to_right", "right_to_left", "custom"),
            state="readonly",
            width=16,
        ).grid(row=3, column=1, sticky="w", padx=5, pady=4)
        self.traj_vars["path_direction"].trace_add("write", lambda *_: self._update_preview())

        self.duration_label = ttk.Label(controls, text="")
        self.duration_label.grid(row=3, column=2, columnspan=4, sticky="w", padx=5, pady=4)

        self.canvas = tk.Canvas(panel, background="#101418", highlightthickness=1, highlightbackground="#8a8f98")
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.canvas.bind("<Configure>", lambda _event: self._update_preview())

    def _load_into_fields(self, design: StimulusDesign) -> None:
        self.name_var.set(design.name)
        self.sofa_var.set(design.sofa_file)
        self.noises = list(design.noises)
        traj = design.trajectory
        for key, var in self.traj_vars.items():
            var.set(str(getattr(traj, key)))
        protocol = design.protocol
        self.protocol_vars["repetitions_per_condition"].set(str(protocol.repetitions_per_condition))
        self.protocol_vars["soa_values_ms"].set(", ".join(str(value) for value in protocol.soa_values_ms))
        self.protocol_vars["spatial_values_cm"].set(", ".join(f"{value:g}" for value in protocol.spatial_values_cm))
        self.protocol_vars["auditory_motion_directions"].set(", ".join(protocol.auditory_motion_directions))
        self.protocol_vars["tactile_sites"].set(", ".join(protocol.tactile_sites))
        self.protocol_vars["catch_trial_percentage"].set(f"{protocol.catch_trial_percentage:g}")
        self.protocol_vars["catch_trials_exact"].set("" if protocol.catch_trials_exact is None else str(protocol.catch_trials_exact))
        self.protocol_vars["baseline_soa_values_ms"].set(", ".join(str(value) for value in protocol.baseline_soa_values_ms))
        self.protocol_vars["respiratory_phases"].set(", ".join(protocol.respiratory_phases))
        self.protocol_vars["blocks"].set(str(protocol.blocks))
        self.protocol_vars["participants"].set(str(protocol.participants))
        self.protocol_vars["random_seed"].set(str(protocol.random_seed))
        self.pair_spatial_values_var.set(protocol.pair_spatial_values_with_soas)
        self.include_baseline_var.set(protocol.include_baseline_trials)
        self._refresh_noise_tree()
        self._update_protocol_summary()

    def _refresh_noise_tree(self) -> None:
        for item in self.noise_tree.get_children():
            self.noise_tree.delete(item)
        for idx, noise in enumerate(self.noises):
            self.noise_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    noise.label,
                    noise.noise_type,
                    f"{noise.azimuth_deg:.1f}",
                    f"{noise.elevation_deg:.1f}",
                    f"{noise.gain:.2f}",
                ),
            )
        if self.noises and not self.noise_tree.selection():
            self.noise_tree.selection_set("0")
            self._noise_selected()

    def _parse_float(self, value: str, label: str) -> float:
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be a number.") from exc

    def _parse_int(self, value: str, label: str) -> int:
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be an integer.") from exc

    def _parse_int_list(self, value: str, label: str) -> list[int]:
        try:
            return [int(part.strip()) for part in value.split(",") if part.strip()]
        except ValueError as exc:
            raise ValueError(f"{label} must be a comma-separated list of integers.") from exc

    def _parse_float_list(self, value: str, label: str) -> list[float]:
        try:
            return [float(part.strip()) for part in value.split(",") if part.strip()]
        except ValueError as exc:
            raise ValueError(f"{label} must be a comma-separated list of numbers.") from exc

    def _parse_string_list(self, value: str) -> list[str]:
        return [part.strip() for part in value.split(",") if part.strip()]

    def _parse_optional_int(self, value: str, label: str) -> int | None:
        value = value.strip()
        if not value:
            return None
        return self._parse_int(value, label)

    def _build_design_from_fields(self) -> StimulusDesign:
        trajectory = TrajectorySpec(
            start_radius_m=self._parse_float(self.traj_vars["start_radius_m"].get(), "Start radius"),
            end_radius_m=self._parse_float(self.traj_vars["end_radius_m"].get(), "End radius"),
            path_direction=self.traj_vars["path_direction"].get(),
            path_length_m=self._parse_float(self.traj_vars["path_length_m"].get(), "Path length"),
            propagation_speed_mps=self._parse_float(self.traj_vars["propagation_speed_mps"].get(), "Speed"),
            azimuth_start_deg=self._parse_float(self.traj_vars["azimuth_start_deg"].get(), "Start azimuth"),
            azimuth_end_deg=self._parse_float(self.traj_vars["azimuth_end_deg"].get(), "End azimuth"),
            elevation_deg=self._parse_float(self.traj_vars["elevation_deg"].get(), "Elevation"),
            padding_pre_s=self._parse_float(self.traj_vars["padding_pre_s"].get(), "Lead padding"),
            padding_post_s=self._parse_float(self.traj_vars["padding_post_s"].get(), "Tail padding"),
        )
        protocol = ProtocolSpec(
            repetitions_per_condition=self._parse_int(self.protocol_vars["repetitions_per_condition"].get(), "Repetitions"),
            soa_values_ms=self._parse_int_list(self.protocol_vars["soa_values_ms"].get(), "SOAs"),
            spatial_values_cm=self._parse_float_list(self.protocol_vars["spatial_values_cm"].get(), "Spatial values"),
            pair_spatial_values_with_soas=self.pair_spatial_values_var.get(),
            auditory_motion_directions=self._parse_string_list(self.protocol_vars["auditory_motion_directions"].get()),
            tactile_sites=self._parse_string_list(self.protocol_vars["tactile_sites"].get()),
            catch_trial_percentage=self._parse_float(self.protocol_vars["catch_trial_percentage"].get(), "Catch percentage"),
            catch_trials_exact=self._parse_optional_int(self.protocol_vars["catch_trials_exact"].get(), "Exact catch count"),
            include_baseline_trials=self.include_baseline_var.get(),
            baseline_soa_values_ms=self._parse_int_list(self.protocol_vars["baseline_soa_values_ms"].get(), "Baseline SOAs"),
            respiratory_phases=self._parse_string_list(self.protocol_vars["respiratory_phases"].get()),
            blocks=self._parse_int(self.protocol_vars["blocks"].get(), "Blocks"),
            participants=self._parse_int(self.protocol_vars["participants"].get(), "Participants"),
            random_seed=self._parse_int(self.protocol_vars["random_seed"].get(), "Seed"),
        )
        return StimulusDesign(
            name=self.name_var.get().strip() or "Untitled PPS stimulus design",
            sofa_file=self.sofa_var.get().strip(),
            noises=list(self.noises),
            trajectory=trajectory,
            protocol=protocol,
        )

    def _noise_selected(self, _event=None) -> None:
        selected = self.noise_tree.selection()
        if not selected:
            return
        noise = self.noises[int(selected[0])]
        self.noise_label_var.set(noise.label)
        self.noise_type_var.set(noise.noise_type)
        self.noise_azimuth_var.set(str(noise.azimuth_deg))
        self.noise_elevation_var.set(str(noise.elevation_deg))
        self.noise_gain_var.set(str(noise.gain))

    def _add_or_update_noise(self) -> None:
        try:
            noise = NoiseDefinition(
                label=self.noise_label_var.get().strip() or self.noise_type_var.get().title(),
                noise_type=self.noise_type_var.get().strip().lower(),
                azimuth_deg=self._parse_float(self.noise_azimuth_var.get(), "Noise azimuth"),
                elevation_deg=self._parse_float(self.noise_elevation_var.get(), "Noise elevation"),
                gain=self._parse_float(self.noise_gain_var.get(), "Noise gain"),
            )
        except ValueError as exc:
            messagebox.showerror("Invalid noise", str(exc))
            return

        selected = self.noise_tree.selection()
        if selected:
            self.noises[int(selected[0])] = noise
        else:
            self.noises.append(noise)
        self._refresh_noise_tree()
        self._update_protocol_summary()
        self.status_var.set("Noise definition updated.")

    def _remove_noise(self) -> None:
        selected = self.noise_tree.selection()
        if not selected:
            return
        del self.noises[int(selected[0])]
        self._refresh_noise_tree()
        self._update_protocol_summary()
        self.status_var.set("Noise definition removed.")

    def _browse_sofa(self) -> None:
        path = filedialog.askopenfilename(
            title="Select SOFA HRIR file",
            filetypes=[("SOFA files", "*.sofa"), ("All files", "*.*")],
        )
        if path:
            self.sofa_var.set(path)

    def _load_template_clicked(self) -> None:
        selected = self.template_combo.current()
        if selected < 0 or selected >= len(self.templates):
            return
        template = self.templates[selected]
        self.design = template.design
        self._load_into_fields(self.design)
        self._update_preview()
        self.status_var.set(f"Loaded template: {template.title} ({template.verification_status})")
        if template.verification_status != "verified":
            messagebox.showwarning(
                "Template needs verification",
                "This template contains partial literature metadata. Confirm the source paper before exact replication.",
            )

    def _validate_sofa(self) -> None:
        path = Path(self.sofa_var.get())
        if not path.exists():
            messagebox.showerror("SOFA file", f"File not found:\n{path}")
            return
        try:
            summary = sofa_summary(path)
        except Exception as exc:
            messagebox.showerror("SOFA file", str(exc))
            return
        msg = (
            f"{summary['positions']} positions\n"
            f"Azimuth: {summary['azimuth_min']:.1f} to {summary['azimuth_max']:.1f} deg\n"
            f"Elevation: {summary['elevation_min']:.1f} to {summary['elevation_max']:.1f} deg\n"
            f"Sample rate: {summary['sample_rate'] or 'unknown'}"
        )
        messagebox.showinfo("SOFA file summary", msg)
        self.status_var.set("SOFA file validated.")

    def _snap_noises(self) -> None:
        try:
            design = snap_noises_to_sofa(self._build_design_from_fields())
        except Exception as exc:
            messagebox.showerror("Snap to SOFA", str(exc))
            return
        self.design = design
        self._load_into_fields(design)
        self.status_var.set("Noise azimuth/elevation values snapped to nearest SOFA positions.")

    def _check_design(self) -> None:
        try:
            design = self._build_design_from_fields()
        except ValueError as exc:
            messagebox.showerror("Invalid design", str(exc))
            return
        warnings = validate_design(design)
        if warnings:
            messagebox.showwarning("Design check", "\n".join(warnings))
            self.status_var.set(f"Design check found {len(warnings)} warning(s).")
        else:
            messagebox.showinfo("Design check", "Design check passed.")
            self.status_var.set("Design check passed.")

    def _update_protocol_summary(self) -> None:
        if not hasattr(self, "protocol_tree"):
            return
        for item in self.protocol_tree.get_children():
            self.protocol_tree.delete(item)
        try:
            design = self._build_design_from_fields()
            summary = protocol_summary(design)
        except Exception:
            return
        labels = [
            ("Audio-tactile trials", "audio_tactile_trials"),
            ("Baseline trials", "baseline_trials"),
            ("Catch trials", "catch_trials"),
            ("Total trials", "total_trials"),
            ("Trials per block", "trials_per_block"),
            ("Participants", "participants"),
            ("Participant-trials", "total_participant_trials"),
        ]
        for label, key in labels:
            self.protocol_tree.insert("", "end", values=(label, summary[key]))

    def _save_clicked(self) -> None:
        try:
            design = self._build_design_from_fields()
        except ValueError as exc:
            messagebox.showerror("Invalid design", str(exc))
            return
        path = filedialog.asksaveasfilename(
            title="Save stimulus design",
            defaultextension=".json",
            initialdir=str(self.design_path.parent),
            initialfile=self.design_path.name,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        self.design_path = Path(path)
        save_design(design, self.design_path)
        self.status_var.set(f"Saved {self.design_path}")

    def _load_clicked(self) -> None:
        path = filedialog.askopenfilename(
            title="Load stimulus design",
            initialdir=str(self.design_path.parent),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        self.design_path = Path(path)
        self.design = load_design(self.design_path)
        self._load_into_fields(self.design)
        self._update_preview()
        self.status_var.set(f"Loaded {self.design_path}")

    def _export_trajectory_clicked(self) -> None:
        try:
            design = self._build_design_from_fields()
        except ValueError as exc:
            messagebox.showerror("Invalid design", str(exc))
            return
        path = filedialog.asksaveasfilename(
            title="Export trajectory CSV",
            defaultextension=".csv",
            initialdir=str(REPO_ROOT / "artifacts"),
            initialfile="stimulus_trajectory.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        export_trajectory_csv(design, Path(path))
        self.status_var.set(f"Exported {path}")

    def _export_protocol_clicked(self) -> None:
        try:
            design = self._build_design_from_fields()
        except ValueError as exc:
            messagebox.showerror("Invalid design", str(exc))
            return
        path = filedialog.asksaveasfilename(
            title="Export protocol CSV",
            defaultextension=".csv",
            initialdir=str(REPO_ROOT / "artifacts"),
            initialfile="stimulus_protocol.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        export_protocol_csv(design, Path(path))
        self.status_var.set(f"Exported {path}")

    def _update_preview(self) -> None:
        if not hasattr(self, "canvas"):
            return
        try:
            design = self._build_design_from_fields()
        except Exception:
            return

        points = trajectory_points(design.trajectory, samples=100)
        movement = design.trajectory.movement_duration_s
        total = design.trajectory.total_duration_s
        self.duration_label.config(text=f"Movement: {movement:.3f}s   Total: {total:.3f}s")

        canvas = self.canvas
        canvas.delete("all")
        w = max(canvas.winfo_width(), 320)
        h = max(canvas.winfo_height(), 240)
        cx, cy = w / 2, h * 0.58
        max_abs = max(
            0.25,
            max(abs(p["x_m"]) for p in points),
            max(abs(p["y_m"]) for p in points),
            design.trajectory.start_radius_m,
            design.trajectory.end_radius_m,
        )
        scale = min(w, h) * 0.38 / max_abs

        for radius in (0.25, 0.5, 1.0, 1.5, 2.0):
            if radius <= max_abs * 1.1:
                r = radius * scale
                canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#28323b")

        canvas.create_line(cx, 16, cx, h - 16, fill="#28323b")
        canvas.create_line(16, cy, w - 16, cy, fill="#28323b")
        canvas.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, fill="#f2f5f7", outline="")
        canvas.create_text(cx, cy + 20, fill="#d9dee5", text="Listener")

        xy = []
        for p in points:
            xy.extend([cx + p["x_m"] * scale, cy - p["y_m"] * scale])
        if len(xy) >= 4:
            canvas.create_line(*xy, fill="#69c7ff", width=3, smooth=True)
        start = points[0]
        end = points[-1]
        canvas.create_oval(cx + start["x_m"] * scale - 6, cy - start["y_m"] * scale - 6, cx + start["x_m"] * scale + 6, cy - start["y_m"] * scale + 6, fill="#79e36d", outline="")
        canvas.create_oval(cx + end["x_m"] * scale - 6, cy - end["y_m"] * scale - 6, cx + end["x_m"] * scale + 6, cy - end["y_m"] * scale + 6, fill="#ff7373", outline="")
        canvas.create_text(18, 18, anchor="nw", fill="#d9dee5", text="Top-down trajectory preview")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the PPS stimulus designer.")
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN_PATH, help="Design JSON to open or create.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    root = tk.Tk()
    StimulusDesignerApp(root, design_path=args.design)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
