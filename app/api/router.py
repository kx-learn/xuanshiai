"""Top-level API router."""

from fastapi import APIRouter

from app.api.routes import health
from app.api.routes import admin, auth, certifications, community, discovery, identity, matchmaker, membership, points, profile, regions, social, users


api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(certifications.router, tags=["certifications"])
api_router.include_router(membership.router, tags=["membership"])
api_router.include_router(points.router, tags=["points"])
api_router.include_router(regions.router, tags=["regions"])
api_router.include_router(identity.router, tags=["identity"])
api_router.include_router(matchmaker.router, tags=["matchmaker"])
api_router.include_router(matchmaker.requests_router, tags=["matchmaker-service"])
api_router.include_router(matchmaker.admin_router, tags=["admin-matchmaker"])
api_router.include_router(profile.router, tags=["profile"])
api_router.include_router(discovery.router, tags=["discovery"])
api_router.include_router(discovery.users_router, tags=["public-profile"])
api_router.include_router(social.router, tags=["social"])
api_router.include_router(community.router, tags=["community"])
api_router.include_router(admin.router, tags=["admin"])
