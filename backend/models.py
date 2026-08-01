# backend/models.py (SQLAlchemy, adjust if you pick something else)
from sqlalchemy import Column, String, Float, Integer, ForeignKey

class Pole(Base):
    __tablename__ = "poles"
    pole_id = Column(String, primary_key=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    feeder_id = Column(String, nullable=False)
    dt_id = Column(String, ForeignKey("transformers.dt_id"), nullable=False)
    seq_on_line = Column(Integer, nullable=True)        # NULL for 60% of DTs
    parent_pole_id = Column(String, nullable=True)      # NULL wherever seq_on_line is
    pole_type = Column(String, nullable=True)
    ward = Column(String, nullable=True)
    pincode = Column(String, nullable=True)              # missing ~3%
    device_id = Column(String, nullable=True)             # missing ~9%

class Transformer(Base):
    __tablename__ = "transformers"
    dt_id = Column(String, primary_key=True)
    feeder_id = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    capacity_kva = Column(Float)
    households_served = Column(Integer)