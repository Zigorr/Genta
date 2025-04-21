# Auth/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Regexp, Email
import re # For password complexity

# Optional: Import your get_user_by_username function if needed for validation
# REMOVED: from Database.database_manager import get_user_by_username
from Database.database_manager import get_user_by_email

# Helper function for email uniqueness validation
def validate_email_unique(form, field):
    if get_user_by_email(field.data):
        raise ValidationError('Email address already registered.')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Login')

class RegistrationForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=1, max=50)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=1, max=50)])
    email = StringField('Email', validators=[
        DataRequired(),
        Email(message='Invalid email address.'),
        Length(max=120),
        validate_email_unique
    ])
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters long.'),
        Regexp(r'.*[A-Z].*', message='Password must contain at least one uppercase letter.'),
        Regexp(r'.*[0-9].*', message='Password must contain at least one numeral.')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match.')
    ])
    submit = SubmitField('Register')

    # Optional: Add custom validator to check if username already exists
    # def validate_username(self, username):
    #     # Make sure to handle database access appropriately here if you enable this
    #     # from Database.database_manager import get_user_by_username 
    #     user = get_user_by_username(username.data)
    #     if user:
    #         raise ValidationError('That username is already taken. Please choose a different one.') 

class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters long.'),
        Regexp(r'.*[A-Z].*', message='Password must contain at least one uppercase letter.'),
        Regexp(r'.*[0-9].*', message='Password must contain at least one numeral.')
    ])
    confirm_new_password = PasswordField('Confirm New Password', validators=[
        DataRequired(),
        EqualTo('new_password', message='New passwords must match.')
    ])
    submit = SubmitField('Change Password')

class VerificationForm(FlaskForm):
    """Form for submitting the 4-digit email verification code."""
    code = StringField('Verification Code', validators=[
        DataRequired(),
        Length(min=4, max=4, message='Code must be 4 digits.'),
        Regexp(r'^[0-9]{4}$' , message='Code must contain only digits.')
    ])
    submit = SubmitField('Verify Account')

# Deprecated/Unused forms related to username
# class ChangeUsernameForm(FlaskForm): ...
# class SetUsernameForm(FlaskForm): ... 