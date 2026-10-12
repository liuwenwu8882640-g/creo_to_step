# Creo Batch Export to STEP

Batch export Creo PRT/ASM models to STEP files using Creo Distributed Batch.

This tool automatically scans Creo models, generates DXC task files, launches Creo Distributed Batch in non-graphics mode, and verifies exported STEP files.

---

## Features

### Automatic Model Discovery

Supports:

- part.prt
- part.prt.1
- part.prt.25
- assembly.asm
- assembly.asm.8

Automatically detects Creo models in a folder.

---

### Latest Version Selection

When multiple versions exist:

```text
plate.prt.1
plate.prt.3
plate.prt.8
```

Only the highest version is exported:

plate.prt.8

## Assembly Support

Supports:

- PRT
- ASM

Assemblies and parts can be processed together.

## Automatic DXC Generation

Automatically creates Creo Distributed Batch DXC files.

No need to manually build export tasks in Creo UI.


## Non-Graphics Batch Processing

Launches:

ptcdbatch.bat


using:

-nographics
-process


for unattended execution.

## Automatic STEP Verification

After export:

- Detect generated STEP files
- Detect generated STP files
- Validate file size
- Report failures

## Detailed Logs

Generates:

_batch_work/

├── step_export_xxx.dxc
├── step_export_xxx.log
└── step_export_xxx_summary.txt


for troubleshooting and auditing.

# Workflow

PRT / ASM Folder
        │
        ▼
Scan Models
        │
        ▼
Select Latest Versions
        │
        ▼
Generate DXC
        │
        ▼
Launch Creo Distributed Batch
        │
        ▼
Export STEP Files
        │
        ▼
Verify Results
        │
        ▼
Create Summary Report

# Requirements

## Software
Creo Parametric
Creo Distributed Batch

Verified with:

Creo 12

## Required Files
ptcdbatch.bat
step_3d_export.ttd


Example:

PTC_DBATCH_BAT = (
    r"C:\PTC\Creo 12.4.3.0"
    r"\Parametric\bin\ptcdbatch.bat"
)

STEP_TTD_FILE = (
    r"C:\PTC\Creo 12.4.3.0"
    r"\Common Files\text\ttds"
    r"\step_3d_export.ttd"
)

# Usage
## Select Folder with GUI
python batch_creo_to_step.py


A folder selection dialog will appear.

## Specify Folder
python batch_creo_to_step.py D:\Models

## Generate DXC Only
python batch_creo_to_step.py D:\Models --dry-run


No conversion will be executed.

Only the DXC file is generated.

## Output Structure
SourceFolder

├── model1.prt
├── model2.asm

└── STP
    ├── model1.stp
    ├── model2.step

    └── _batch_work
        ├── step_export.dxc
        ├── step_export.log
        └── summary.txt

## Configuration

Important settings:

RECURSIVE_SCAN = False


Whether to scan subfolders.

ONLY_LATEST_VERSION = True


Only process the highest Creo version.

PREFER_NUMBERED_VERSION = True


Prefer versioned models.

OVERWRITE_EXISTING_STEP = True


Replace existing STEP files.

## Notes

This program does NOT parse Creo proprietary files.

Actual STEP conversion is performed by:

Creo Distributed Batch


The script only:

- scans models
- prepares tasks
- generates DXC
- launches Creo
- verifies outputs

For ASM export, all dependent parts must be accessible by Creo.

# Example Applications

- PRT → STEP batch conversion
- ASM → STEP batch conversion
- CAD migration workflows
- PLM data export
- STEP preprocessing before FreeCAD automation
- STEP preprocessing before DXF generation

# Author

liuwenwu8882640-g


