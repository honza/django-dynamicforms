import itertools
from re import compile
from datetime import datetime

from django.contrib import admin
from django.contrib.auth.models import User
from django.db import models
from django import forms
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.conf import settings

from utils import get_class


class QuestionTypeRegisterError(Exception):
    """
    Raised when a question type set in ``DYNAMICFORMS_CUSTOM_TYPES`` can't be
    registered.
    """
    pass


DYNAMICFORMS_CUSTOM_TYPES = getattr(settings, 'DYNAMICFORMS_CUSTOM_TYPES', {})


DEFAULT_QUESTION_TYPES = (
    'dynamicforms.models.DynamicTextQuestion',
    'dynamicforms.models.DynamicYesNoQuestion',
    'dynamicforms.models.DynamicMultipleChoiceQuestion',
    'dynamicforms.models.DynamicRatingQuestion',
)


class InheritanceResolveModel(models.Model):
    """
    An abstract base class that provides a ``real_type`` FK to ContentType.

    For use in trees of inherited models, to be able to downcast
    parent instances to their child types.

    http://stackoverflow.com/questions/929029/how-do-i-access-the-child-classe
    s-of-an-object-in-django-without-knowing-the-name
    """
    real_type = models.ForeignKey(ContentType, editable=False, null=True,
            related_name="%(app_label)s_%(class)s_inheritance_related")

    def save(self, *args, **kwargs):
        if not self.id:
            self.real_type = self._get_real_type()
        super(InheritanceResolveModel, self).save(*args, **kwargs)

    def _get_real_type(self):
        return ContentType.objects.get_for_model(type(self))

    def resolve(self):
        try:
            return self.real_type.get_object_for_this_type(pk=self.pk)
        except AttributeError:
            raise AttributeError(
                "Failed to access real type for %s with self.real_type=%s" %
                    (self, self.real_type))

    class Meta:
        abstract = True


class DynamicForm(models.Model):
    name = models.CharField(max_length=255)
    questions = generic.GenericRelation('DynamicFormQuestion')

    def admin_url(self):
        return '/admin/dynamicforms/dynamicform/%d/' % self.id

    def __unicode__(self):
        return self.name


###############################################################################
# Questions
###############################################################################


class DynamicFormQuestion(InheritanceResolveModel):
    question_text = models.TextField()
    content_type = models.ForeignKey(ContentType, related_name="content_types")
    object_id = models.PositiveIntegerField()
    parent_object = generic.GenericForeignKey('content_type', 'object_id')
    order = models.IntegerField(default=1000)

    class Meta:
        ordering = ['order', 'id']

    def __unicode__(self):
        return "%s..." % self.question_text[:20]

    def admin_url(self):
        return '/admin/dynamicforms/%s/%d/' % (self.real_type.model, self.id)

    @classmethod
    def pretty_name(cls):
        raise NotImplementedError(
                "You should resolve me first before you ask me my name")

    def display(self, user):
        raise NotImplementedError("I don't know how to display myself.")

    @classmethod
    def save_response(cls, user, question_id, response, response_set):
        raise NotImplementedError("My name is %s and I don't know how to save a response."
                % cls)

    def get_type(self):
        return str(self._get_real_type())

    def get_form_name(self):
        """
        """
        return '%s-%d' % (self._meta.module_name, self.id,)


class DynamicTextQuestion(DynamicFormQuestion):

    @classmethod
    def pretty_name(cls):
        return "Text question"

    def display(self, user):
        f = forms.CharField(label=self.question_text, widget=forms.Textarea)
        return f, self.get_form_name()

    @classmethod
    def save_response(cls, user, question_id, response, response_set):
        q = cls.objects.get(pk=question_id)
        DynamicTextResponse.objects.create(
            user=user,
            question=q,
            dynamic_response_set=response_set,
            text_response=response
        )


class DynamicMultipleChoiceAnswer(models.Model):
    question = models.ForeignKey('DynamicMultipleChoiceQuestion')
    answer_text = models.TextField()


class DynamicMultipleChoiceQuestion(DynamicFormQuestion):

    choice_class = DynamicMultipleChoiceAnswer
    PATTERN = compile(r'^([a-z-]+)-([0-9]+)$')

    @classmethod
    def pretty_name(cls):
        return "Multiple choice question"

    def get_choices(self):
        answers = self.dynamicmultiplechoiceanswer_set.all()
        name = 'dynamic-multiple-choice-answer-%d'
        return [(name % a.pk, a.answer_text,) for a in answers]

    def display(self, user):
        f = forms.MultipleChoiceField(label=self.question_text,
                widget=forms.widgets.CheckboxSelectMultiple(),
                choices=self.get_choices())
        return f, self.get_form_name()

    @classmethod
    def save_response(cls, user, question_id, responses, response_set):
        q = cls.objects.get(pk=question_id)
        if responses:
            for r in responses:
                meta = cls.PATTERN.findall(r)[0]
                answer = DynamicMultipleChoiceAnswer.objects.get(id=meta[1])
                models.DynamicMultipleChoiceResponse.objects.create(
                        user=user,
                        question=q,
                        dynamic_response_set=response_set,
                        answer=answer)


class DynamicYesNoQuestion(DynamicMultipleChoiceQuestion):

    @classmethod
    def pretty_name(cls):
        return "Yes/No question"

    def display(self, user):
        choices = [
            ('yes', 'Yes',),
            ('no', 'No',),
        ]
        f = forms.ChoiceField(label=self.question_text,
                widget=forms.widgets.RadioSelect(),
                choices=choices)
        return f, self.get_form_name()

    @classmethod
    def save_response(cls, user, question_id, response, response_set):
        q = cls.objects.get(pk=question_id)
        DynamicYesNoResponse.objects.create(
            user=user,
            question=q,
            response=True if response == 'yes' else False,
            dynamic_response_set=response_set
        )



class DynamicRatingQuestion(DynamicMultipleChoiceQuestion):
    
    @classmethod
    def pretty_name(cls):
        return "Rating question"

    def get_choices(self):
        answers = self.dynamicratinganswer_set.all()
        name = 'dynamic-rating-answer-%d'
        return [(name % a.pk, a.answer_text,) for a in answers]

    def display(self, user):
        f = forms.ChoiceField(label=self.question_text,
                widget=forms.widgets.RadioSelect(),
                choices=self.get_choices())
        return f, self.get_form_name()




class DynamicRatingAnswer(models.Model):
    question = models.ForeignKey(DynamicRatingQuestion)
    answer_text = models.TextField()

    def __unicode__(self):
        return self.answer_text

###############################################################################
# Responses
###############################################################################


class DynamicResponseSet(models.Model):
    user = models.ForeignKey(User)
    dynamic_form = models.ForeignKey(DynamicForm)
    added = models.DateTimeField(auto_now_add=True)
    interviewer = models.ForeignKey(User, null=True, related_name="responsesets_as_interviewer")

    def __unicode__(self):
        t = self.added.strftime("%m/%d/%y")
        return "%s' responses to %s (%s)" % (self.user.username,
                self.dynamic_form.name, t)

    @property
    def responses(self):
        return list(list(self.dynamicmultiplechoiceresponse_set.all()) + \
            list(self.dynamictextresponse_set.all()) +
            list(self.dynamicratingresponse_set.all()) + \
            list(self.dynamicyesnoresponse_set.all()))


class DynamicResponse(models.Model):
    user = models.ForeignKey(User)
    submitted = models.DateTimeField(default=datetime.utcnow())
    dynamic_response_set = models.ForeignKey(DynamicResponseSet)

    class Meta:
        abstract = True


class DynamicTextResponse(DynamicResponse):
    text_response = models.TextField()
    question = models.ForeignKey(DynamicTextQuestion)

    def __unicode__(self):
        return self.text_response


class DynamicMultipleChoiceResponse(DynamicResponse):
    question = models.ForeignKey(DynamicMultipleChoiceQuestion)
    answer = models.ForeignKey(DynamicMultipleChoiceAnswer)

    def __unicode__(self):
        return self.answer.answer_text


class DynamicYesNoResponse(DynamicResponse):
    question = models.ForeignKey(DynamicYesNoQuestion)
    response = models.BooleanField()

    def __unicode__(self):
        if self.response:
            return 'Yes'
        else:
            return 'No'


class DynamicRatingResponse(DynamicResponse):
    question = models.ForeignKey(DynamicRatingQuestion)
    response = models.ForeignKey(DynamicRatingAnswer)

    def __unicode__(self):
        return self.response.answer_text


##############################################################################
# Magic follows
##############################################################################


def register_questions_types(*tuples):
    """
    Take a list of tuples and return a list of ``dicts``.  Each ``dict``
    contains the following keys:

        * ``pretty_name`` - Human-readable name of question type
        * ``slug``        - Url-safe name of question type
        * ``class``       - class definition
    """
    types = list(itertools.chain(*tuples))
    question_types = []
    for t in types:
        try:
            class_ = get_class(t, QuestionTypeRegisterError)
        except QuestionTypeRegisterError:
            print 'Failed to register %s' % t
            continue
        question_types.append({
            'pretty_name': class_.pretty_name(),
            'slug': class_._meta.module_name,
            'class': class_
        })
    return question_types


QUESTION_TYPES = register_questions_types(DEFAULT_QUESTION_TYPES,
        DYNAMICFORMS_CUSTOM_TYPES)


def _get_creation_choices():
    """
    Get choices for the *Add content* drop down in the admin.
    """
    # TODO:  Use url reversal rather than hard-wiring URL
    choices = [('', '------')]
    for question_type in QUESTION_TYPES:
        app_label = question_type['class']._meta.app_label
        c = ('/admin/%s/%s/add/' % (app_label, question_type['slug']),
                question_type['pretty_name'])
        choices.append(c)
    return choices


CHOICES = _get_creation_choices()
from admin import DynamicFormQuestionAdmin


def register_admin():
    """
    Register question types in Django admin
    """
    for t in QUESTION_TYPES:
        class_ = t['class']
        class admin_class(DynamicFormQuestionAdmin):
            model = class_

        if hasattr(class_, 'choice_class'):
            inline_class = admin.StackedInline
            inline_class.model = class_.choice_class
            admin_class.inlines = [inline_class]

        admin.site.register(class_, admin_class)


register_admin()
