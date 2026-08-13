# Copyright (c) 2026 Lumine. All rights reserved.

"""LLM Gateway database models."""

from datetime import datetime
from enum import Enum
import logging
from typing import Optional
from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship
import sys
import os

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

from lumine.data.session import get_db_session
from lumine.data.models import Base, LLMUsage
