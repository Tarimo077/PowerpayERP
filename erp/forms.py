from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import validate_password, password_validators_help_text_html
from django.contrib.auth.models import User
from django.db import transaction
from django.utils.text import slugify
from .models import Department, Document, DocumentTemplate, Organization, Profile, Task, Timesheet, TimesheetEntry, UserInvite

class StyledForm:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput): 
                field.widget.attrs["class"] = "checkbox checkbox-primary"
            elif isinstance(field.widget, forms.Select): 
                field.widget.attrs["class"] = "select select-bordered w-full"
            elif isinstance(field.widget, forms.Textarea): 
                field.widget.attrs["class"] = "textarea textarea-bordered w-full"
            else: 
                field.widget.attrs["class"] = "input input-bordered w-full"

class RegistrationForm(StyledForm, UserCreationForm):
    organization_name = forms.CharField(max_length=180)
    business_email = forms.EmailField()
    industry = forms.CharField(max_length=100, required=False)
    phone = forms.CharField(max_length=40, required=False)
    email = forms.EmailField()
    first_name = forms.CharField(max_length=80)
    last_name = forms.CharField(max_length=80)

    class Meta(UserCreationForm.Meta): 
        model = User
        fields = ("organization_name", "business_email", "industry", "phone", "first_name", "last_name", "email", "password1", "password2")

    def clean_email(self):
        email=self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists(): raise forms.ValidationError("An account with this email already exists.")
        return email

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        if commit:
            user.save()
            base = slugify(self.cleaned_data["organization_name"])
            slug = base
            n = 2
            while Organization.objects.filter(slug=slug).exists(): 
                slug = f"{base}-{n}"
                n += 1
            org = Organization.objects.create(name=self.cleaned_data["organization_name"], slug=slug, business_email=self.cleaned_data["business_email"], industry=self.cleaned_data["industry"], phone=self.cleaned_data["phone"])
            Profile.objects.create(user=user, organization=org, role="admin", employee_id="ADMIN-001", position="Organization Administrator")
        return user

class EmployeeForm(StyledForm, forms.ModelForm):
    first_name = forms.CharField(max_length=80)
    last_name = forms.CharField(max_length=80)
    email = forms.EmailField()
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput, required=False, help_text="Required for new employees")

    class Meta: 
        model = Profile
        fields = ["first_name", "last_name", "email", "username", "password", "employee_id", "phone", "position", "department", "manager", "role", "hire_date"]
        widgets = {"hire_date": 
        forms.DateInput(attrs={"type": 
        "date"})}

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["department"].queryset = Department.objects.filter(organization=organization)
        self.fields["manager"].queryset = Profile.objects.filter(organization=organization, role__in=["admin", "manager"])
        if self.instance.pk:
            u=self.instance.user
            for k in ["first_name","last_name","email","username"]: 
                self.fields[k].initial=getattr(u,k)

    def clean_username(self):
        qs=User.objects.filter(username=self.cleaned_data["username"])
        if self.instance.pk: 
            qs=qs.exclude(pk=self.instance.user_id)
        if qs.exists(): 
            raise forms.ValidationError("This username is already in use.")
        return self.cleaned_data["username"]

    @transaction.atomic
    def save(self, commit=True):
        p=super().save(False)
        if p.pk: 
            u=p.user
        else: 
            u=User()
        for k in ["first_name","last_name","email","username"]: 
            setattr(u,k,self.cleaned_data[k])
        if self.cleaned_data.get("password"): 
            u.set_password(self.cleaned_data["password"])
        elif not u.pk: 
            u.set_unusable_password()
        if commit: 
            u.save()
            p.user=u
            p.organization=self.organization
            p.full_clean()
            p.save()
        return p

class TaskForm(StyledForm, forms.ModelForm):
    class Meta: 
        model=Task
        fields=["title","description","instructions","assigned_to","department","priority","status","start_date","due_date","attachment"]
        widgets={"start_date":forms.DateInput(attrs={"type":"date"}),"due_date":forms.DateInput(attrs={"type":"date"})}

    def __init__(self,*args,organization=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.organization=organization
        self.fields["assigned_to"].queryset=Profile.objects.filter(organization=organization,user__is_active=True)
        self.fields["department"].queryset=Department.objects.filter(organization=organization)

class TimesheetForm(StyledForm, forms.ModelForm):
    class Meta: 
        model=Timesheet
        fields=["period_start","period_end"]
        widgets={"period_start":forms.DateInput(attrs={"type":"date"}),"period_end":forms.DateInput(attrs={"type":"date"})}

    def clean(self):
        d=super().clean()
        if d.get("period_start") and d.get("period_end") and d["period_start"]>d["period_end"]: 
            self.add_error("period_end","End date must follow start date.")
        return d

class EntryForm(StyledForm, forms.ModelForm):
    class Meta: 
        model=TimesheetEntry
        fields=["date","task","task_performed","hours","description","notes","supporting_document"]
        widgets={"date":forms.DateInput(attrs={"type":"date"})}

    def __init__(self,*args,organization=None,**kwargs): 
        super().__init__(*args,**kwargs)
        self.fields["task"].queryset=Task.objects.filter(organization=organization)

class DocumentForm(StyledForm, forms.ModelForm):
    class Meta: 
        model=Document
        fields=["title","category","file","visibility","department","owner"]

    def __init__(self,*args,organization=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields["department"].queryset=Department.objects.filter(organization=organization)
        self.fields["owner"].queryset=Profile.objects.filter(organization=organization)

class TemplateForm(StyledForm, forms.ModelForm):
    class Meta: 
        model=DocumentTemplate
        fields=["name","file","department","is_default"]

    def __init__(self,*args,organization=None,**kwargs): 
        super().__init__(*args,**kwargs)
        self.fields["department"].queryset=Department.objects.filter(organization=organization)

class DepartmentForm(StyledForm, forms.ModelForm):
    class Meta: 
        model=Department
        fields=["name","description"]

class EmailLoginForm(StyledForm, forms.Form):
    email=forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete":"email","placeholder":"you@example.com"}))
    password=forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete":"current-password"}))

class OTPForm(StyledForm, forms.Form):
    otp=forms.CharField(min_length=6,max_length=6,widget=forms.TextInput(attrs={"inputmode":"numeric","autocomplete":"one-time-code","placeholder":"000000"}))
    def clean_otp(self):
        value=self.cleaned_data["otp"]
        if not value.isdigit(): raise forms.ValidationError("Enter the six-digit code.")
        return value

class SetInvitePasswordForm(StyledForm, forms.Form):
    first_name=forms.CharField(max_length=80); last_name=forms.CharField(max_length=80)
    password1=forms.CharField(label="Password",help_text=password_validators_help_text_html(),widget=forms.PasswordInput(attrs={"autocomplete":"new-password"}))
    password2=forms.CharField(label="Confirm password",widget=forms.PasswordInput(attrs={"autocomplete":"new-password"}))
    def __init__(self,*args,email=None,**kwargs): 
        super().__init__(*args,**kwargs); self.email=email
    def clean_password1(self):
        password=self.cleaned_data["password1"]; validate_password(password,User(email=self.email or "")); return password
    def clean(self):
        data=super().clean()
        if data.get("password1") and data.get("password1")!=data.get("password2"): 
            self.add_error("password2","The two passwords do not match.")
        return data

class EmployeeForm(StyledForm, forms.ModelForm):
    """Employment details only; account credentials are chosen after invitation."""
    class Meta: model=UserInvite; fields=["email","role","department","position","manager"]
    def __init__(self,*args,organization=None,**kwargs):
        super().__init__(*args,**kwargs); self.organization=organization
        self.fields["department"].queryset=Department.objects.filter(organization=organization)
        self.fields["manager"].queryset=Profile.objects.filter(organization=organization,role__in=["admin","manager"])
        self.fields["role"].choices=[("manager","Manager"),("employee","Employee")]
    def clean_email(self):
        email=self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists(): raise forms.ValidationError("This employee already has an account.")
        if UserInvite.objects.filter(email__iexact=email,organization=self.organization,is_used=False).exists(): raise forms.ValidationError("An activation invitation is already pending for this employee.")
        return email
