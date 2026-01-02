from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe
from .models import Post, Comment, LinkPost, Profile, InfoPost

class CharCountTextarea(forms.Textarea):
    def render(self, name, value, attrs=None, renderer=None):
        final_attrs = self.build_attrs(self.attrs, attrs)
        html = super().render(name, value, attrs, renderer)
        field_id = final_attrs.get('id', f'id_{name}')
        max_length = final_attrs.get('maxlength', 500)
        
        counter_html = f'''
        <div id="{field_id}_counter" class="text-end text-muted small mt-1">0 / {max_length}</div>
        <script>
            (function() {{
                var textarea = document.getElementById('{field_id}');
                var counter = document.getElementById('{field_id}_counter');
                if (textarea && counter) {{
                    var update = function() {{
                        counter.textContent = textarea.value.length + ' / {max_length}';
                    }};
                    textarea.addEventListener('input', update);
                    update();
                }}
            }})();
        </script>
        '''
        return mark_safe(html + counter_html)

class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['title', 'content']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 10}),
        }

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class InfoPostForm(forms.ModelForm):
    class Meta:
        model = InfoPost
        fields = ['title', 'content', 'author']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'content': CharCountTextarea(attrs={'class': 'form-control', 'rows': 3, 'maxlength': '500', 'placeholder': '내용을 입력하세요 (최대 500자)'}),
            'author': forms.TextInput(attrs={'class': 'form-control'}),
        }

class ThreadPostForm(InfoPostForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['content'].max_length = 140
        self.fields['content'].widget.attrs['maxlength'] = '140'
        self.fields['content'].widget.attrs['placeholder'] = '내용을 입력하세요 (최대 140자)'

class LinkPostForm(forms.ModelForm):
    url = forms.URLField(widget=forms.URLInput(attrs={'class': 'form-control'}), required=True)
    class Meta:
        model = LinkPost
        fields = ['category', 'title', 'url', 'author']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'url': forms.URLInput(attrs={'class': 'form-control'}),
            'author': forms.TextInput(attrs={'class': 'form-control'}),
        }

class SignUpForm(forms.ModelForm):
    email = forms.EmailField(label="이메일", widget=forms.EmailInput(attrs={'class': 'form-control'}))
    password = forms.CharField(label="비밀번호", widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    nickname = forms.CharField(label="닉네임", widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ['email', 'password']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(username=email).exists():
            raise ValidationError("이미 사용 중인 이메일입니다.")
        return email

    def clean_nickname(self):
        nickname = self.cleaned_data.get('nickname')
        if Profile.objects.filter(nickname=nickname).exists():
            raise ValidationError("이미 사용 중인 닉네임입니다.")
        return nickname

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['email']
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
            Profile.objects.create(user=user, nickname=self.cleaned_data['nickname'])
        return user

class LoginForm(forms.Form):
    email = forms.EmailField(label="이메일", widget=forms.EmailInput(attrs={'class': 'form-control'}))
    password = forms.CharField(label="비밀번호", widget=forms.PasswordInput(attrs={'class': 'form-control'}))

class PasswordResetForm(forms.Form):
    email = forms.EmailField(label="이메일", widget=forms.EmailInput(attrs={'class': 'form-control'}))
    nickname = forms.CharField(label="닉네임", widget=forms.TextInput(attrs={'class': 'form-control'}))

class PasswordChangeForm(forms.Form):
    new_password = forms.CharField(label="새 비밀번호", widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    confirm_password = forms.CharField(label="비밀번호 확인", widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("new_password")
        p2 = cleaned_data.get("confirm_password")
        if p1 and p2 and p1 != p2:
            raise ValidationError("비밀번호가 일치하지 않습니다.")
        return cleaned_data
