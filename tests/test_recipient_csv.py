import pytest
import mock
import itertools
from flask import Markup

from notifications_utils.recipients import RecipientCSV, Columns
from notifications_utils.template import Template


@pytest.mark.parametrize(
    "file_contents,template_type,expected",
    [
        (
            """
                phone number,name
                +44 123, test1
                +44 456,test2
            """,
            "sms",
            [
                mock.ANY,
                mock.ANY
            ]
        ),
        (
            """
                email address,name
                test@example.com,test1
                test2@example.com, test2
            """,
            "email",
            [
                mock.ANY,
                mock.ANY
            ]
        )
    ]
)
def test_get_rows(file_contents, template_type, expected):
    assert list(RecipientCSV(file_contents, template_type=template_type).rows) == expected


@pytest.mark.parametrize(
    "file_contents,template_type,expected",
    [
        (
            """
                phone number,name
                07700900460, test1
                +447700 900 460,test2
                ,
            """,
            'sms',
            [
                {
                    'columns': mock.ANY,
                    'index': 0,
                    'message_too_long': False
                },
                {
                    'columns': mock.ANY,
                    'index': 1,
                    'message_too_long': False
                },
            ]
        ),
        (
            """
                email address,name,colour
                test@example.com,test1,blue
                example.com, test2,red
            """,
            'email',
            [
                {
                    'columns': mock.ANY,
                    'index': 0,
                    'message_too_long': False
                },
                {
                    'columns': mock.ANY,
                    'index': 1,
                    'message_too_long': False
                },
            ]
        )
    ]
)
def test_get_annotated_rows(file_contents, template_type, expected):
    recipients = RecipientCSV(
        file_contents,
        template_type=template_type,
        placeholders=['name'],
        max_initial_rows_shown=1
    )
    assert list(recipients.annotated_rows) == expected
    assert len(list(recipients.annotated_rows)) == 2
    assert len(list(recipients.initial_annotated_rows)) == 1


def test_get_annotated_rows_with_errors():
    recipients = RecipientCSV(
        """
            email address, name
            a@b.com,
            a@b.com,
            a@b.com,
            a@b.com,
            a@b.com,
            a@b.com,


        """,
        template_type='email',
        placeholders=['name'],
        max_errors_shown=3
    )
    assert len(list(recipients.annotated_rows_with_errors)) == 6
    assert len(list(recipients.initial_annotated_rows_with_errors)) == 3


def test_big_list():
    big_csv = RecipientCSV(
        "email address,name\n" + ("a@b.com\n"*100000),
        template_type='email',
        placeholders=['name'],
        max_errors_shown=100,
        max_initial_rows_shown=3
    )
    assert len(list(big_csv.initial_annotated_rows)) == 3
    assert len(list(big_csv.initial_annotated_rows_with_errors)) == 100
    assert len(list(big_csv.rows)) == 100000


@pytest.mark.parametrize(
    "file_contents,template_type,placeholders,expected_recipients,expected_personalisation",
    [
        (
            """
                phone number,name, date
                +44 123,test1,today
                +44456,    ,tomorrow
                ,,
                , ,
            """,
            'sms',
            ['name'],
            ['+44 123', '+44456'],
            [{'name': 'test1'}, {'name': ''}]
        ),
        (
            """
                email address,name,colour
                test@example.com,test1,red
                testatexampledotcom,test2,blue
            """,
            'email',
            ['colour'],
            ['test@example.com', 'testatexampledotcom'],
            [
                {'colour': 'red'},
                {'colour': 'blue'}
            ]
        )
    ]
)
def test_get_recipient(file_contents, template_type, placeholders, expected_recipients, expected_personalisation):
    recipients = RecipientCSV(file_contents, template_type=template_type, placeholders=placeholders)

    recipients_recipients = list(recipients.recipients)
    recipients_and_personalisation = list(recipients.recipients_and_personalisation)
    personalisation = list(recipients.personalisation)

    for index, row in enumerate(expected_personalisation):
        for key, value in row.items():
            assert recipients_recipients[index] == expected_recipients[index]
            assert personalisation[index].get(key) == value
            assert recipients_and_personalisation[index][1].get(key) == value


@pytest.mark.parametrize(
    "file_contents,template_type,expected,expected_highlighted,expected_missing",
    [
        (
            "", 'sms', [], [], set(['phone number', 'name'])
        ),
        (
            """
                phone number,name
                07700900460,test1
                07700900460,test1
                07700900460,test1
            """,
            'sms',
            ['phone number', 'name'],
            ['phone number', Markup('<span class=\'placeholder\'>name</span>')],
            set()
        ),
        (
            """
                email address,name,colour
            """,
            'email',
            ['email address', 'name', 'colour'],
            ['email address', Markup('<span class=\'placeholder\'>name</span>'), 'colour'],
            set()
        ),
        (
            """
                email address,colour
            """,
            'email',
            ['email address', 'colour'],
            ['email address', 'colour'],
            set(['name'])
        )
    ]
)
def test_column_headers(file_contents, template_type, expected, expected_highlighted, expected_missing):
    recipients = RecipientCSV(file_contents, template_type=template_type, placeholders=['name'])
    assert recipients.column_headers == expected
    assert recipients.column_headers_with_placeholders_highlighted == expected_highlighted
    assert recipients.missing_column_headers == expected_missing
    assert recipients.has_errors == bool(expected_missing)


@pytest.mark.parametrize(
    "file_contents,rows_with_bad_recipients,rows_with_missing_data",
    [
        (
            """
                phone number,name,date
                07700900460,test1,test1
                07700900460,test1
                +44 123,test1,test1
                07700900460,test1,test1
                07700900460,test1
                +44 123,test1,test1
            """,
            {2, 5}, {1, 4}
        ),
        (
            """
            """,
            set(), set()
        )
    ]
)
def test_bad_or_missing_data(file_contents, rows_with_bad_recipients, rows_with_missing_data):
    recipients = RecipientCSV(file_contents, template_type='sms', placeholders=['date'])
    assert recipients.rows_with_bad_recipients == rows_with_bad_recipients
    assert recipients.rows_with_missing_data == rows_with_missing_data
    assert recipients.has_errors is True


@pytest.mark.parametrize(
    "file_contents,template_type,whitelist,count_of_rows_with_errors",
    [
        (
            """
                phone number
                07700900460
                07700900461
                07700900462
                07700900463
            """,
            'sms',
            ['+447700900460'],  # Same as first phone number but in different format
            3
        ),
        (
            """
                phone number
                7700900460
                447700900461
                07700900462
            """,
            'sms',
            ['07700900460', '07700900461', '07700900462', '07700900463', 'test@example.com'],
            0
        ),
        (
            """
                email address
                IN_WHITELIST@EXAMPLE.COM
                not_in_whitelist@example.com
            """,
            'email',
            ['in_whitelist@example.com', '07700900460'],  # Email case differs to the one in the CSV
            1
        )
    ]
)
def test_recipient_whitelist(file_contents, template_type, whitelist, count_of_rows_with_errors):

    recipients = RecipientCSV(
        file_contents,
        template_type=template_type,
        whitelist=whitelist
    )
    assert len(recipients.rows_with_errors) == count_of_rows_with_errors

    # Make sure the whitelist isn’t emptied by reading it. If it’s an iterator then
    # there’s a risk that it gets emptied after being read once
    recipients.whitelist = (str(fake_number) for fake_number in range(7700900888, 7700900898))
    list(recipients.whitelist)
    assert len(recipients.rows_with_errors)

    # An empty whitelist is treated as no whitelist at all
    recipients.whitelist = []
    assert len(recipients.rows_with_errors) == 0
    recipients.whitelist = itertools.chain()
    assert len(recipients.rows_with_errors) == 0


def test_detects_rows_which_result_in_overly_long_messages():
    recipients = RecipientCSV(
        """
            phone number,placeholder
            07700900460,1
            07700900461,1234567890
            07700900462,12345678901
            07700900463,123456789012345678901234567890
        """,
        template_type='sms',
        template=Template({'content': '((placeholder))', 'type': 'sms'}, content_character_limit=10)
    )
    assert recipients.rows_with_errors == {2, 3}
    assert recipients.rows_with_message_too_long == {2, 3}


@pytest.mark.parametrize(
    "key, expected",
    sum([
        [(key, expected) for key in group] for expected, group in [
            ('07700900460', (
                'phone number',
                '   PHONENUMBER',
                'phone_number',
                'phone-number',
                'phoneNumber'
            )),
            ('Jo', (
                'FIRSTNAME',
                'first name',
                'first_name ',
                'first-name',
                'firstName'
            )),
            ('Bloggs', (
                'Last    Name',
                'LASTNAME',
                '    last_name',
                'last-name',
                'lastName   '
            ))
        ]
    ], [])
)
def test_ignores_spaces_and_case_in_placeholders(key, expected):
    recipients = RecipientCSV(
        """
            phone number,FIRSTNAME, Last Name
            07700900460, Jo, Bloggs
        """,
        placeholders=['phone_number', 'First Name', 'lastname'],
        template_type='sms'
    )
    first_row = list(recipients.annotated_rows)[0]
    assert first_row['columns'].get(key)['data'] == expected
    assert first_row['columns'][key]['data'] == expected
    assert list(recipients.personalisation)[0][key] == expected
    assert list(recipients.recipients) == ['07700900460']

    assert len(first_row['columns'].items()) == 3

    assert recipients.missing_column_headers == set()
    recipients.placeholders = {'one', 'TWO', 'Thirty_Three'}
    assert recipients.missing_column_headers == {'one', 'TWO', 'Thirty_Three'}
