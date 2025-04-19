# Auth/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Regexp
import re # For password complexity

# Optional: Import your get_user_by_username function if needed for validation
# from Database.database_manager import get_user_by_username

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Login')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
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