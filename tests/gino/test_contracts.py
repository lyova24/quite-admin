"""Exercise exactly the same public contracts as the other built-in adapters."""

# ruff: noqa: F401

# Re-exported tests retain their parameterizations; fixtures come from this directory.
from tests.test_adapter_safety import (
    test_does_not_assign_model_attributes_or_primary_keys,
    test_null_and_large_integer_round_trip,
    test_rejects_unsafe_queries_before_data_access,
    test_requires_exact_complete_primary_keys,
    test_search_values_are_bound_literals,
)
from tests.test_adapters import (
    test_discovery_crud_search_pagination_and_rollback,
    test_filter_values_are_bound,
    test_literal_search_wildcards,
    test_rejects_filter_operators_and_column_expressions,
    test_schema_keys_are_typed,
    test_service_adapter_keeps_writes_behind_business_rules,
    test_typed_filters_and_projection,
)
from tests.test_concurrency import test_checked_write_contract
from tests.test_relations import (
    test_checked_relationship_changes_are_atomic,
    test_create_with_forward_and_collection_relationships,
    test_inline_relationship_fields_share_the_record_save,
    test_read_only_users_can_filter_by_related_records,
    test_related_filters_count_before_pagination_and_combine_with_scalars,
    test_related_queries_share_filter_sort_and_projection_contract,
    test_relationship_contract_and_atomic_rollback,
    test_searchable_picker_pagination_and_permissions,
)
