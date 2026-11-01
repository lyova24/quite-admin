"""Private HTTP handlers sharing the state and authorization helpers of Admin.

Keep the public facade in admin.py; these mixins do not own application state.
Metadata and permission checks stay request-local so host changes remain visible.
"""
