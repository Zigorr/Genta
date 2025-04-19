# Auth/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Regexp
import re # For password complexity

# Optional: Import your get_user_by_username function if needed for validation
from Database.database_manager import get_user_by_username

# Helper function for username validation
def validate_username_unique(form, field):
    if get_user_by_username(field.data):
        raise ValidationError('Username already taken. Please choose a different one.')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Login')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(), 
        Length(min=4, max=25), 
        Regexp(r'^[a-zA-Z0-9]+$', message="Username must contain only letters and numbers (no spaces)."),
        validate_username_unique
    ])
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters long.'),
        # Ensure regex uses double backslashes for escaping within the string
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

class ChangeUsernameForm(FlaskForm):
    username = StringField('New Username', validators=[
        DataRequired(), 
        Length(min=4, max=25), 
        Regexp(r'^[a-zA-Z0-9]+$', message="Username must contain only letters and numbers (no spaces)."),
        validate_username_unique
    ])
    submit = SubmitField('Change Username')

    # Optional: Add validator to check if new username is different from current
    # def validate_username(self, username):
    #     if username.data == current_user.username: # Requires importing current_user
    #         raise ValidationError('New username must be different from the current one.')
        # You might also re-check uniqueness here, although the DB and route handler will do it.

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

class SetUsernameForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(), 
        Length(min=4, max=25), 
        Regexp(r'^[a-zA-Z0-9]+$', message="Username must contain only letters and numbers (no spaces)."),
        validate_username_unique
    ])
    submit = SubmitField('Set Username')

    # Add validator to check if username already exists
    def validate_username(self, username):
        # Needs access to the database check function
        user = get_user_by_username(username.data)
        if user:
            raise ValidationError('That username is already taken. Please choose a different one.') 