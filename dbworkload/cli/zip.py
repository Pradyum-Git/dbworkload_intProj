#!/usr/bin/python

from pathlib import Path
from typing import Optional
import dbworkload.models.util
import dbworkload.utils.common
from dbworkload.cli.dep import Param, EPILOG
import typer
from enum import Enum

class DataGenMode(str, Enum):
    SIMPLE = "simple"            # old behaviour
    CONSTRAINT_AWARE = "constraint-aware"   # new behaviour


app = typer.Typer(
    epilog=EPILOG,
    no_args_is_help=True,
    help="Build workload from a CockroachDB debug zip directory.",
)


@app.command(
    "init",
    epilog=EPILOG,
    no_args_is_help=True,
    help="Initialize a workload from a debug.zip directory (create schema, generate data, load data, setup workload)",
)
def util_init(
    zip_dir: Optional[Path] = typer.Option(
        ...,
        "--zip_dir",
        "-z",
        help="Location of the debug zip directory",
        exists=True,
        dir_okay=True,
        writable=False,
        readable=True,
        resolve_path=True,
    ),
    db_name: Optional[str] = typer.Option(
        ...,
        "--db_name",
        "-d",
        help="Database name",
    ),
    cloud_storage_uri: Optional[str] = typer.Option(
        ...,
        "--cloud_storage_uri",
        "-c",
        help="Google Cloud storage uri to use as temporary storage for CSV file upload",
    ),
    cluster_url: Optional[str] = typer.Option(
        ...,
        "--cluster_url",
        "-u",
        help="URL to database cluster (used for data upload)",
    ),
    anon: bool = typer.Option(
        False,
        "--anonymize",
        "-a",
        help="Whether or not to anonymize the workload",
    ),
    data_gen_mode: DataGenMode = typer.Option(          # ← NEW FLAG
        DataGenMode.SIMPLE,
        "--data-gen-mode", "-m",
        case_sensitive=False,
        help="Data-generation strategy: "
             "'simple' (legacy util_yaml/util_csv) "
             "or 'constraint-aware' (util_yaml_ca/util_csv_ca).",
        show_default=True,
    ),
):
    dbworkload.models.util.init(zip_dir, db_name, cloud_storage_uri, cluster_url, anon, data_gen_mode)


@app.command(
    "list",
    epilog=EPILOG,
    no_args_is_help=True,
    help="Lists the databases present in the debug zip",
)
def util_init(
    zip_dir: Optional[Path] = typer.Option(
        ...,
        "--zip_dir",
        "-z",
        help="Location of the debug zip directory",
        exists=True,
        dir_okay=True,
        writable=False,
        readable=True,
        resolve_path=True,
    ),
):
    dbworkload.models.util.zip_list(zip_dir)
