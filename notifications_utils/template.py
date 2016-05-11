import re
import math

from orderedset import OrderedSet
from flask import Markup


class Template():

    placeholder_pattern = r"\(\(([^\)\(]+)\)\)"  # anything that looks like ((registration number))
    placeholder_tag = "<span class='placeholder'>{}</span>"

    def __init__(
        self,
        template,
        values=None,
        drop_values=(),
        prefix=None,
        encoding="utf-8",
        content_character_limit=None
    ):
        if not isinstance(template, dict):
            raise TypeError('Template must be a dict')
        if values is not None and not isinstance(values, dict):
            raise TypeError('Values must be a dict')
        if prefix is not None and not isinstance(prefix, str):
            raise TypeError('Prefix must be a string')
        self.id = template.get("id", None)
        self.name = template.get("name", None)
        self.content = template["content"]
        self.values = (values or {}).copy()
        self.template_type = template.get('template_type', None)
        self.subject = template.get('subject', None)
        for value in drop_values:
            self.values.pop(value, None)
        self.prefix = prefix if self.template_type == 'sms' else None
        self.encoding = encoding
        self.content_character_limit = content_character_limit
        self._template = template

    def __str__(self):
        if self.values:
            return self.replaced
        return self.content

    def __repr__(self):
        return "{}(\"{}\", {})".format(self.__class__.__name__, self.content, self.values)  # TODO: more real

    @property
    def formatted(self):
        return self.__add_prefix(nl2br(re.sub(
            Template.placeholder_pattern,
            lambda match: Template.placeholder_tag.format(match.group(1)),
            self.content
        )))

    @property
    def formatted_subject(self):
        return self.__add_prefix(nl2br(re.sub(
            Template.placeholder_pattern,
            lambda match: Template.placeholder_tag.format(match.group(1)),
            self.subject)))

    @property
    def formatted_subject_as_markup(self):
        return Markup(self.formatted_subject)

    @property
    def formatted_as_markup(self):
        return Markup(self.formatted)

    @property
    def placeholders(self):
        return OrderedSet(re.findall(
            Template.placeholder_pattern,
            (self.subject or '') + self.content))

    @property
    def placeholders_as_markup(self):
        return [
            Markup(Template.placeholder_tag.format(placeholder))
            for placeholder in self.placeholders
        ]

    @property
    def replaced(self):
        if self.missing_data:
            raise NeededByTemplateError(self.missing_data)
        return self.__add_prefix(re.sub(
            Template.placeholder_pattern,
            lambda match: self.values.get(match.group(1)),
            self.content
        ))

    @property
    def replaced_content_count(self):
        return len(self.replaced.encode(self.encoding))

    @property
    def content_count(self):
        return len(self.content.encode(self.encoding))

    @property
    def sms_fragment_count(self):
        if self.template_type != 'sms':
            raise TypeError("The template needs to have a template type of 'sms'")
        return get_sms_fragment_count(self.replaced_content_count)

    @property
    def content_too_long(self):
        return (
            self.content_character_limit is not None and
            self.replaced_content_count > self.content_character_limit
        )

    @property
    def replaced_govuk_escaped(self):
        return unlink_govuk_escaped(self.replaced)

    @property
    def replaced_subject(self):
        if self.missing_data:
            raise NeededByTemplateError(self.missing_data)
        return re.sub(
            Template.placeholder_pattern,
            lambda match: self.values.get(match.group(1)),
            self.subject if self.subject else "")

    @property
    def as_HTML_email(self):
        return re.sub(
            r'EMAIL_BODY',
            nl2br(self.replaced_govuk_escaped),
            govuk_email_wrapper
        )

    @property
    def missing_data(self):
        return list(
            placeholder for placeholder in self.placeholders
            if self.values.get(placeholder) is None
        )

    @property
    def additional_data(self):
        return self.values.keys() - self.placeholders

    def __add_prefix(self, output):
        if self.prefix:
            return "{}: {}".format(self.prefix.strip(), output)
        return output

    def get_raw(self, key, default=None):
        return self._template.get(key, default)


def nl2br(value):
    return re.sub(r'\n|\r', '<br>', value.strip())


class NeededByTemplateError(Exception):
    def __init__(self, keys):
        super(NeededByTemplateError, self).__init__(", ".join(keys))


class NoPlaceholderForDataError(Exception):
    def __init__(self, keys):
        super(NoPlaceholderForDataError, self).__init__(", ".join(keys))


govuk_email_wrapper = '''
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html>

<head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
  <meta content="telephone=no" name="format-detection"> <!-- need to add formatting for real phone numbers -->
  <title>Page title</title>

  <style>
    @media only screen and (min-device-width: 581px) {
      .content {
        width: 580px !important;
      }
    }
  </style>
</head>

<body style="font-family: Helvetica, Arial, sans-serif;font-size: 16px;margin: 0;color:#0b0c0c;">

<!--[if (gte mso 9)|(IE)]>
  <table width="580" align="center" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td>
<![endif]-->
     <table width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
        <td width="100%" height="53" bgcolor="#0b0c0c">
            <table width="580" cellpadding="0" cellspacing="0" border="0" align="center">
                <tr>
                    <td width="70" bgcolor="#0b0c0c" valign="middle">
                        <a href="https://www.gov.uk" style="text-decoration: none;"><img
                            src="https://www.notifications.service.gov.uk/static/images/email-template/crown-32px.gif"
                            alt="" height="32" border="0"></a>
                    </td>
                    <td width="100%" bgcolor="#0b0c0c" valign="middle" align="left">
<span style="padding-left: 5px;"><a href="https://www.gov.uk" style="
    font-family: Helvetica, Arial, sans-serif;
    font-size: 28px;
    line-height: 1.315789474;
    font-weight: 700;
    color: #ffffff;
    text-decoration: none;
"
>GOV.UK</a></span></a>
                    </td>
                </tr>
            </table>
        </td>
    </tr>
</table>


        <table
            class="content"
            align="center"
            cellpadding="0"
            cellspacing="0"
            border="0"
            style="width: 100%; max-width: 580px;"
        >
          <tr>
            <td height="30">&nbsp;</td>
          </tr>
          <tr>
            <td style="font-family: Helvetica, Arial, sans-serif; font-size: 19px; line-height: 1.315789474;">
              EMAIL_BODY
            </td>
          </tr>
            <tr>
              <td height="30">&nbsp;</td>
            </tr>
        </table>

<!--[if (gte mso 9)|(IE)]>
      </td>
    </tr>
</table>
<![endif]-->

</body>
</html>
'''


govuk_not_a_link = re.compile(
    r'(?<!\.|\/)(GOV)\.(UK)(?!\/|\?)',
    re.IGNORECASE
)


def unlink_govuk_escaped(message):
    return re.sub(
        govuk_not_a_link,
        r'\1' + '.\u200B' + r'\2',  # Unicode zero-width space
        message
    )


def get_sms_fragment_count(character_count):
    return 1 if character_count <= 160 else math.ceil(float(character_count) / 153)
