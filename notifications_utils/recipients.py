import re
import sys
import csv
from contextlib import suppress
from functools import lru_cache

from flask import Markup

from notifications_utils.template import Template
from notifications_utils.columns import Columns


first_column_heading = {
    'email': 'email address',
    'sms': 'phone number'
}


# liberated from https://github.com/clones/wtforms/blob/da7a918c/wtforms/validators.py#L214
# with minor tweaks for SES compatibility - don't allow any spaces, double quotes or semicolons, or
# multiple @ signs (we also don't allow consecutive ..s) [to prevent technical failures]. Also don't allow underscores
# in the domain as that's also banned
email_regex = re.compile(r'^[^\s";@]+@[^\s";@_]*\.[a-z]{2,10}$', flags=re.IGNORECASE)


class RecipientCSV():

    reader_options = {
        'quoting': csv.QUOTE_NONE,
        'skipinitialspace': True
    }

    max_rows = 50000

    def __init__(
        self,
        file_data,
        template_type=None,
        placeholders=None,
        max_errors_shown=20,
        max_initial_rows_shown=10,
        whitelist=None,
        template=None,
        remaining_messages=sys.maxsize
    ):
        self.file_data = file_data.strip(', \n\r\t')
        self.template_type = template_type
        self.placeholders = placeholders
        self.max_errors_shown = max_errors_shown
        self.max_initial_rows_shown = max_initial_rows_shown
        self.whitelist = whitelist
        self.template = template if isinstance(template, Template) else None
        self.annotated_rows = list(self.get_annotated_rows())
        self.remaining_messages = remaining_messages

    @property
    def whitelist(self):
        return self._whitelist

    @whitelist.setter
    def whitelist(self, value):
        try:
            self._whitelist = list(value)
        except TypeError:
            self._whitelist = []

    @property
    def placeholders(self):
        return self._placeholders

    @placeholders.setter
    def placeholders(self, value):
        try:
            self._placeholders = list(value)
            self.placeholders_as_column_keys = [
                Columns.make_key(placeholder) for placeholder in value
            ]
        except TypeError:
            self._placeholders, self.placeholders_as_column_keys = [], []

    @property
    def template_type(self):
        return self._template_type

    @template_type.setter
    def template_type(self, value):
        self._template_type = value
        self.recipient_column_header = first_column_heading[self.template_type]

    @property
    def has_errors(self):
        return bool(
            self.missing_column_headers or
            self.more_rows_than_can_send or
            self.too_many_rows or
            (not self.allowed_to_send_to) or
            self.rows_with_missing_data or
            self.rows_with_bad_recipients or
            self.rows_with_message_too_long
        )  # This is 3x faster than using `any()`

    @property
    def allowed_to_send_to(self):
        if not self.whitelist:
            return True
        return all(
            allowed_to_send_to(recipient, self.whitelist)
            for recipient in self.recipients
        )

    @property
    def rows(self):
        for row in csv.DictReader(
            self.file_data.strip().splitlines(),
            **RecipientCSV.reader_options
        ):
            yield Columns(row)

    @property
    def rows_with_errors(self):
        return self.rows_with_missing_data | self.rows_with_bad_recipients | self.rows_with_message_too_long

    @property
    def rows_with_missing_data(self):
        return set(
            row['index'] for row in self.annotated_rows if any(
                str(key) not in Columns.make_key(self.recipient_column_header) and value.get('error')
                for key, value in row['columns'].items()
            )
        )

    @property
    def rows_with_bad_recipients(self):
        return set(
            row['index']
            for row in self.annotated_rows
            if row['columns'].get(self.recipient_column_header, {}).get('error')
        )

    @property
    def rows_with_message_too_long(self):
        return set(
            row['index'] for row in self.annotated_rows if row['message_too_long']
        )

    @property
    def more_rows_than_can_send(self):
        return len(self.annotated_rows) > self.remaining_messages

    @property
    def too_many_rows(self):
        return len(self.annotated_rows) > self.max_rows

    def get_annotated_rows(self):
        for row_index, row in enumerate(self.rows):
            if self.template:
                self.template.values = dict(row.items())
            yield dict(
                columns=Columns({key: {
                    'data': value,
                    'error': self._get_error_for_field(key, value),
                    'ignore': (
                        key != Columns.make_key(self.recipient_column_header) and
                        key not in self.placeholders_as_column_keys
                    )
                } for key, value in row.items()}),
                index=row_index,
                message_too_long=bool(self.template and self.template.content_too_long)
            )

    @property
    def initial_annotated_rows(self):
        for row in self.annotated_rows:
            if row['index'] < self.max_initial_rows_shown:
                yield row

    @property
    def annotated_rows_with_errors(self):
        for row in self.annotated_rows:
            if RecipientCSV.row_has_error(row):
                yield row

    @property
    def initial_annotated_rows_with_errors(self):
        for row_index, row in enumerate(self.annotated_rows_with_errors):
            if row_index < self.max_errors_shown:
                yield row

    @property
    def recipients(self):
        for row in self.rows:
            yield self._get_recipient_from_row(row)

    @property
    def personalisation(self):
        for row in self.rows:
            yield self._get_personalisation_from_row(row)

    @property
    def enumerated_recipients_and_personalisation(self):
        for row_index, row in enumerate(self.rows):
            yield (
                row_index,
                self._get_recipient_from_row(row),
                self._get_personalisation_from_row(row)
            )

    @property
    def recipients_and_personalisation(self):
        for row in self.rows:
            yield (
                self._get_recipient_from_row(row),
                self._get_personalisation_from_row(row)
            )

    @property
    def column_headers(self):
        for row in csv.reader(
            self.file_data.strip().splitlines(),
            **RecipientCSV.reader_options
        ):
            return row
        return []

    @property
    def missing_column_headers(self):
        required = {
            Columns.make_key(key): key
            for key in set([self.recipient_column_header] + self.placeholders)
        }
        return set(
            required[key] for key in set(
                [Columns.make_key(self.recipient_column_header)] + self.placeholders_as_column_keys
            ) - set(
                Columns.make_key(column_header) for column_header in self.column_headers
            )
        )

    @property
    def has_recipient_column(self):
        return Columns.make_key(self.recipient_column_header) in set(
            Columns.make_key(column_header) for column_header in self.column_headers
        )

    @property
    def column_headers_with_placeholders_highlighted(self):
        return [
            Markup(Template.placeholder_tag.format(header, '')) if header in self.placeholders else header
            for header in self.column_headers
        ]

    def _get_error_for_field(self, key, value):

        if key == Columns.make_key(self.recipient_column_header):
            try:
                validate_recipient(value, self.template_type)
            except (InvalidEmailError, InvalidPhoneError) as error:
                return str(error)

        if key not in self.placeholders_as_column_keys:
            return

        if value in [None, '']:
            return 'Missing'

    def _get_recipient_from_row(self, row):
        return row[
            self.recipient_column_header
        ]

    def _get_personalisation_from_row(self, row):
        return Columns({
            key: value for key, value in row.items() if key in self.placeholders_as_column_keys
        })

    @staticmethod
    def row_has_error(row):
        return any(
            key != 'index' and value.get('error') for key, value in row['columns'].items()
        )


class InvalidEmailError(Exception):
    def __init__(self, message):
        self.message = message


class InvalidPhoneError(InvalidEmailError):
    pass


def validate_phone_number(number):

    for character in ['(', ')', ' ', '-']:
        number = number.replace(character, '')

    number = number.lstrip('+').lstrip('0')

    try:
        list(map(int, number))
    except ValueError:
        raise InvalidPhoneError('Must not contain letters or symbols')

    if not any(
        number.startswith(prefix)
        for prefix in ['7', '07', '447', '4407', '00447']
    ):
        raise InvalidPhoneError('Not a UK mobile number')

    # Split number on first 7
    number = number.split('7', 1)[1]

    if len(number) > 9:
        raise InvalidPhoneError('Too many digits')

    if len(number) < 9:
        raise InvalidPhoneError('Not enough digits')

    return number


def format_phone_number(number):
    return '+447{}'.format(number)


def format_phone_number_human_readable(number):
    return '07{} {} {}'.format(*re.findall('...', number))


def validate_and_format_phone_number(number, human_readable=False):
    if human_readable:
        return format_phone_number_human_readable(validate_phone_number(number))
    return format_phone_number(validate_phone_number(number))


def validate_email_address(email_address):
    if not re.match(email_regex, email_address) or '..' in email_address:
        raise InvalidEmailError('Not a valid email address')
    return email_address


def format_email_address(email_address):
    return email_address.strip().lower()


def validate_and_format_email_address(email_address):
    return format_email_address(validate_email_address(email_address))


def validate_recipient(recipient, template_type):
    return {
        'email': validate_email_address,
        'sms': validate_phone_number
    }[template_type](recipient)


@lru_cache(maxsize=32, typed=False)
def format_recipient(recipient):
    with suppress(InvalidPhoneError):
        return validate_and_format_phone_number(recipient)
    with suppress(InvalidEmailError):
        return validate_and_format_email_address(recipient)
    return recipient


def allowed_to_send_to(recipient, whitelist):
    return format_recipient(recipient) in [
        format_recipient(recipient) for recipient in whitelist
    ]
