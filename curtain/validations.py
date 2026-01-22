import six
from filters.schema import base_query_params_schema
from filters.validations import IntegerLike, DatetimeWithTZ, GenericSeparatedValidator

curtain_query_schema = base_query_params_schema.extend(
    {
        "id": IntegerLike(),
        "link_id": six.text_type,
        "created": DatetimeWithTZ(),
        "username": six.text_type,
        "name": six.text_type,
        "description": six.text_type,
        "curtain_type": GenericSeparatedValidator(str, ",")
    }
)

kinase_library_query_schema = base_query_params_schema.extend(
    {
        "id": IntegerLike(),
        "entry": six.text_type,
        "position": IntegerLike(),
        "residue": six.text_type,
    }
)

data_filter_list_query_schema = base_query_params_schema.extend(
    {
        "id": IntegerLike(),
        #"name": six.text_type,
        #"data": six.text_type
        "name__exact": six.text_type,
        "category__exact": six.text_type,
    }
)