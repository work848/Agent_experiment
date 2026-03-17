from pydantic import BaseModel
from typing import Dict, List, Optional


class FunctionInfo(BaseModel):

    name: str
    file: str
    args: List[str]
    docstring: Optional[str]
    code: str
    calls: List[str]


class ClassInfo(BaseModel):

    name: str
    file: str
    methods: List[str]
    docstring: Optional[str]


class FileInfo(BaseModel):

    path: str
    functions: List[str]
    classes: List[str]
    imports: List[str]


class Workspace(BaseModel):

    root: str

    files: List[str]

    functions: Dict[str, FunctionInfo]

    classes: Dict[str, ClassInfo]

    files_info: Dict[str, FileInfo]

    call_graph: Dict[str, List[str]]

    last_scan: Optional[str]