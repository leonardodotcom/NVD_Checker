import sqlite3

from fastapi import APIRouter, HTTPException

from .. import db
from ..models import Keyword, KeywordIn, Project, ProjectIn

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _require(project_id: int) -> Project:
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.get("", response_model=list[Project])
def list_projects():
    return db.list_projects()


@router.post("", response_model=Project, status_code=201)
def create_project(body: ProjectIn):
    try:
        return db.create_project(body.name)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "A project with this name already exists")


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: int):
    return _require(project_id)


@router.put("/{project_id}", response_model=Project)
def rename_project(project_id: int, body: ProjectIn):
    _require(project_id)
    try:
        return db.rename_project(project_id, body.name)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "A project with this name already exists")


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int):
    if not db.delete_project(project_id):
        raise HTTPException(404, "Project not found")


@router.post("/{project_id}/keywords", response_model=Keyword, status_code=201)
def add_keyword(project_id: int, body: KeywordIn):
    _require(project_id)
    if not body.term.strip():
        raise HTTPException(422, "Keyword cannot be blank")
    try:
        return db.add_keyword(project_id, body.term, body.exact_match)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Keyword already in this project")


@router.delete("/{project_id}/keywords/{keyword_id}", status_code=204)
def delete_keyword(project_id: int, keyword_id: int):
    if not db.delete_keyword(project_id, keyword_id):
        raise HTTPException(404, "Keyword not found")
