import click
import functools
import boto3
import yaml
import json
import subprocess
import botocore.exceptions
import os.path
import pyperclip
from botocore import UNSIGNED
from botocore.client import Config

from .colors import colors
import textwrap

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

# Constants
templates_bucket = 'nclouds-cloudformation-templates'
session = {}
yaml_configs = {}

def common_params(func):
    @click.option('--region', 'region', help="AWS region")
    @click.option('--profile', 'profile', help="AWS profile name")
    @click.option('-e', '--environment', 'env', default='dev', show_default=True, help="The environment for the stack")
    @click.argument('location', default='.', type=click.Path(exists=True))
    @click.argument('extra-args', nargs=-1)
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        global session
        global yaml_configs 

        yaml_configs = _loadYamlFile('.config')
        kwargs['region'] = kwargs['region'] or _getConfiguration('region', kwargs['env'])
        kwargs['profile'] = kwargs['profile'] or _getConfiguration('profile', kwargs['env'])
        kwargs['bucket'] = _getConfiguration('bucket', kwargs['env'])
        kwargs['parameters'] = _getConfiguration('parameters_file', kwargs['env']) or '{}.json'.format(kwargs['env'])
        kwargs['multi_region'] = _getConfiguration('multi_region', kwargs['env'])
        if kwargs['multi_region'] == True:
            kwargs['bucket'] += '-' + kwargs['region']

        kwargs['base_stack_name'] = _getConfiguration('stack_name', kwargs['env'])
        kwargs['stack_name'] = '{}-{}'.format(kwargs['base_stack_name'], kwargs['env'])

        kwargs['extra_args'] = list(kwargs['extra_args'])

        session = boto3.session.Session(region_name=kwargs['region'], profile_name=kwargs['profile'])
        return func(*args, **kwargs)
    return wrapper

@click.group()
@click.pass_context
def cf(ctx):
    """nClouds thin wrapper over the AWS CLI for CloudFormation"""
    # ctx.obj = { 'hola': 'mundo' }
    pass

@cf.command()
@common_params
# @click.pass_obj
def sync(**kwargs):
    """Sync CloudFormation templates to S3 bucket"""

    key = kwargs['stack_name'] + '/' + kwargs['env']
    command = ['aws', 's3', 'sync', kwargs['location'], 's3://{bucket}/{key}'.format(bucket=kwargs['bucket'], key=key) ,'--exclude', '*', '--include', '*.yml', '--acl', 'bucket-owner-full-control']

    _printInfo(Bucket=kwargs['bucket'], Key=key)
    _executeAwsCliCommand(command, kwargs)

@cf.command()
@common_params
@click.option('-f', '--filename', 'filename', default='master.yml', show_default=True, help="File name of the master template")
@click.option('-w', '--wait', 'wait', is_flag=True, help="Wait until the operation finishes")
def create(**kwargs):
    """Create CloudFormation Stack"""

    command = ['aws', 'cloudformation', 'create-stack', '--stack-name', kwargs['stack_name'], '--template-body', 'file://{}/{}'.format(kwargs['location'], kwargs['filename']), '--parameters', 'file://{}/{}'.format(kwargs['location'], kwargs['parameters']), '--capabilities', 'CAPABILITY_NAMED_IAM', 'CAPABILITY_AUTO_EXPAND']

    _printInfo(Stack=kwargs['stack_name'], Environment=kwargs['env'], Region=kwargs['region'], Bucket=kwargs['bucket'])
    _executeAwsCliCommand(command, kwargs)

    if kwargs['wait']:
        cf_client = session.client('cloudformation')
        waiter = cf_client.get_waiter('stack_create_complete')
        try:
            click.echo(click.style('Waiting for the Stack creation to finish...', fg='blue'))
            waiter.wait(
                StackName=kwargs['stack_name'],
            )
            click.echo(click.style('Stack created successfully', fg='green'))
        except botocore.exceptions.WaiterError as ex:
            click.echo(click.style('The Stack creation failed' , fg='red'))

@cf.command()
@common_params
@click.option('-f', '--filename', 'filename', default='master.yml', show_default=True, help="File name of the master template")
@click.option('-w', '--wait', 'wait', is_flag=True, help="Wait until the operation finishes")
def update(**kwargs):
    """Update CloudFormation Stack"""

    command = ['aws', 'cloudformation', 'update-stack', '--stack-name', kwargs['stack_name'], '--template-body', 'file://{}/{}'.format(kwargs['location'], kwargs['filename']), '--parameters', 'file://{}/{}'.format(kwargs['location'], kwargs['parameters']), '--capabilities', 'CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND']

    _printInfo(Stack=kwargs['stack_name'], Environment=kwargs['env'], Region=kwargs['region'], Bucket=kwargs['bucket'])
    _executeAwsCliCommand(command, kwargs)

    if kwargs['wait']:
        cf_client = session.client('cloudformation')
        waiter = cf_client.get_waiter('stack_update_complete')

        try:
            click.echo(click.style('Waiting for the Stack update to finish...', fg='blue'))
            waiter.wait(
                StackName=kwargs['stack_name'],
            )
            click.echo(click.style('Stack updated successfully', fg='green'))
        except botocore.exceptions.WaiterError as ex:
            click.echo(click.style('The Stack update failed' , fg='red'))

@cf.command()
@common_params
@click.option('-w', '--wait', 'wait', is_flag=True, help="Wait until the operation finishes")
def delete(**kwargs):
    """Delete CloudFormation Stack"""

    command = ['aws', 'cloudformation', 'delete-stack', '--stack-name', kwargs['stack_name']]

    if click.confirm(click.style('Are you sure you want to delete the stack: {}'.format(kwargs['stack_name']), fg='yellow')):
        _printInfo(Stack=kwargs['stack_name'], Environment=kwargs['env'], Region=kwargs['region'], Bucket=kwargs['bucket'])
        _executeAwsCliCommand(command, kwargs)
        click.echo(click.style('The stack is being deleted', fg='blue'))

        if kwargs['wait']:
            cf_client = session.client('cloudformation')
            waiter = cf_client.get_waiter('stack_delete_complete')

            try:
                click.echo(click.style('Waiting for the Stack deletion to finish...', fg='blue'))
                waiter.wait(
                    StackName=kwargs['stack_name'],
                )
                click.echo(click.style('Stack deleted successfully', fg='green'))
            except botocore.exceptions.WaiterError as ex:
                click.echo(click.style('Stack deletion failed' , fg='red'))

@cf.command()
@common_params
@click.option('-f', '--filename', 'filename', default='master.yml', show_default=True, help="File name of the master template")
def info(**kwargs):
    """Print settings used by the CLI"""
    key = kwargs['stack_name'] + '/' + kwargs['env']
    _printInfo(Stack=kwargs['stack_name'], Environment=kwargs['env'], Region=kwargs['region'], Bucket=kwargs['bucket'], Key=key)

@cf.command("list-templates", short_help='List available templates')
def list_templates(**kwargs):
    """List available templates from the nClouds CloudFormation repository"""
    s3 = boto3.resource('s3', config=Config(signature_version=UNSIGNED))
    bucket = s3.Bucket(templates_bucket)

    try:
        templates_metadata = yaml.safe_load(bucket.Object('meta/templates.yml').get()['Body'].read())
        click.echo(click.style('Available templates:' , fg='blue'))

        for key, template in templates_metadata.items():
            click.echo('○ {} - {}'.format(key.ljust(20,' '), _fill_with_padding(template['short-description'], width=75, padding=25)))
    except Exception as ex:
        print(ex)
        click.echo(click.style('Templates are not available at this moment' , fg='yellow'))

@cf.command("list-examples", short_help='List available examples')
def list_examples(**kwargs):
    """List available examples from the nClouds CloudFormation repository"""
    s3 = boto3.resource('s3', config=Config(signature_version=UNSIGNED))
    bucket = s3.Bucket(templates_bucket)

    try:
        examples_metadata = yaml.safe_load(bucket.Object('meta/examples.yml').get()['Body'].read())
        click.echo(click.style('Available examples:' , fg='blue'))

        for key, template in examples_metadata.items():
            click.echo('○ {} - {}'.format(key.ljust(20,' '), _fill_with_padding(template['short-description'], width=75, padding=25)))
    except Exception as ex:
        print(ex)
        click.echo(click.style('Examples are not available at this moment' , fg='yellow'))

@cf.command("get-templates", short_help='Download templates from repository')
@click.option('-s', '--snippet', 'snippet', is_flag=True, help="Copy master stack snippet to the clipboard")
@click.option('-o', '--overwrite', 'overwrite', is_flag=True, help="Overwrite template if it already exists")
@click.argument('templates', nargs=-1)
def get_templates(templates, snippet, overwrite):
    """Download templates from the nClouds CloudFormation repository"""
    s3 = boto3.resource('s3', config=Config(signature_version=UNSIGNED))
    bucket = s3.Bucket(templates_bucket)

    try:
        templates_metadata = yaml.safe_load(bucket.Object('meta/templates.yml').get()['Body'].read())
        click.echo(click.style('Downloading templates...' , fg='blue'))

        if not os.path.exists('templates'):
            os.makedirs('templates')

        master_snippet = ''
        for template in templates:
            obj = bucket.Object('templates/' + templates_metadata[template]['file'])
            if os.path.isfile(obj.key) and overwrite:
                obj.download_file(obj.key)
                click.echo(obj.key + " overwritten")
            elif os.path.isfile(obj.key):
                click.echo(obj.key + " skipped")
            else:
                obj.download_file(obj.key)
                click.echo(obj.key + " created")

            master_snippet += templates_metadata[template]['master-snippet']
        
        if snippet:
            pyperclip.copy(master_snippet)
            click.echo(click.style('Master template snippet copied to clipboard!' , fg='green'))
    except KeyError as ex:
        click.echo(click.style('The template {} doesn\'t exist in nClouds CloudFormation repository'.format(template) , fg='red'))
    except botocore.exceptions.ClientError as ex:
        click.echo(click.style('Templates are not available at this moment' , fg='yellow'))
    except Exception as ex:
        print(ex)
        exit(1)

@cf.command(short_help='Initialize project to use with the cli')
@click.option('--from', 'from_project', default='None', prompt="Enter the nClouds CloudFormation sample project name to start from", show_default=True, help="nClouds CloudFormation sample project")
@click.option('--stack-name', 'stack_name', prompt="Enter the Stack name for the project", help="Stack name for the project")
@click.option('--bucket', 'bucket_name', prompt="Enter the S3 bucket name for the templates", help="S3 bucket name for the templates")
@click.option('--region', 'region', prompt="Enter the AWS region for the CloudFormation Stack", help="AWS region for the CloudFormation Stack")
def init(from_project, stack_name, bucket_name, region):
    """Initialize a new project within the current directory by creating a .config file,
    optionally initialize project using a nClouds sample project"""
    s3 = boto3.resource('s3', config=Config(signature_version=UNSIGNED))
    bucket = s3.Bucket(templates_bucket)

    if os.path.isfile('.config'):
        click.echo(click.style('The current project is already initialized' , fg='red'))
        exit(1)

    data = {
        "global": {
            "stack_name": stack_name,
            "bucket": bucket_name,
            "region": region
        }
    }

    if from_project != 'None':
         # TODO create a metadata file in the repository with the available examples
        try:
            templates_metadata = yaml.safe_load(bucket.Object('meta/examples.yml').get()['Body'].read())
            if from_project.lower() not in templates_metadata:
                click.echo(click.style('The example {} doesn\'t exists in nClouds sample projects repostory'.format(from_project) , fg='red'))
                exit(1)
            click.echo(click.style('Initializing project with \'{}\' sample ...'.format(from_project), fg='blue'))
        except botocore.exceptions.ClientError as ex:
            click.echo(click.style('Templates are not available at this moment' , fg='yellow'))
    else:
        click.echo(click.style('Initializing project with config file', fg='blue'))
    
    
    # Write configuration file
    with open('.config', 'w') as outfile:
        yaml.dump(data, outfile)
        click.echo('.config created')

    if from_project != 'None':
        # Download sample files
        for obj_summary in bucket.objects.filter(Prefix='examples/' + from_project.lower()):
            local_key = obj_summary.key.replace("examples/" + from_project.lower() + "/", "")
            path, filename = os.path.split(local_key)        
            obj = bucket.Object(obj_summary.key)

            if path != '':
                if not os.path.exists(path):
                    os.makedirs(path)
            obj.download_file(local_key)

            click.echo(local_key + " created")
        # Change bucket name in parameters file
        with open("dev.json", "r+") as jsonFile:
            data = json.load(jsonFile)
            for parameter in data:
                if parameter['ParameterKey'] == 'S3BucketName':
                    parameter['ParameterValue'] = bucket_name
            jsonFile.seek(0)
            json.dump(data, jsonFile, indent=2)
            jsonFile.truncate()



# ############################### Helper Methods ###############################

def _fill_with_padding(text, width=25, padding=20):
    text = textwrap.wrap(text, width=width)
    for i in range(1, len(text)):
        text[i] = " " * 25 + text[i]
    return "\n".join(text)

def _printInfo(nl=True, **kwargs):
    message = ''
    for key, value in kwargs.items():
        message += colors['CYAN'] + key + ': ' + colors['BLUE'] + value + colors['CYAN'] +'; '
    message += colors['NORMAL'] + ('\n' if nl == True else '')
    click.echo(message)

def _loadYamlFile(file_name):
    """Parses yaml files and returns its content"""
    try:
        with open(file_name, "r") as file:
            yaml_file = yaml.safe_load(file.read())
            return yaml_file
    except Exception as ex:
        click.echo(click.style('Invalid {} yaml file'.format(file_name), fg='red'))
        print(ex)
        exit(1)

def _loadJsonFile(file_name):
    """Parses json files and returns its content"""
    try:
        with open(file_name, "r") as file:
            json_file = json.load(file)
            return json_file
    except Exception as ex:
        click.echo(click.style('Invalid {} json file'.format(file_name), fg='red'))
        print(ex)
        exit(1)

def _getConfiguration(property, env):
    return yaml_configs.get(env, {}).get(property) or yaml_configs.get('global', {}).get(property)

# def _getRegionProfileString(region, profile):
#     return ([ '--region', region ] if region != None else []) + ([ '--profile', profile ] if profile != None else [])

def _executeAwsCliCommand(command, kwargs):
    final_command = command + ([ '--region', kwargs['region'] ] if kwargs['region'] != None else []) + ([ '--profile', kwargs['profile'] ] if kwargs['profile'] != None else []) + kwargs['extra_args']
    _executeShellCommand(final_command)

def _executeShellCommand(command):
    process = subprocess.Popen(command, universal_newlines=True)
    process.communicate()

    # while True:
    #     output = process.stdout.readline()
    #     # click.echo("hola")
    #     # click.echo(output.strip())
    #     return_code = process.poll()
    #     if return_code is not None:
    #         for output in process.stdout.readlines():
    #             # click.echo(output.strip())
    #             pass
    #         break





class SafeUnknownConstructor(yaml.constructor.SafeConstructor):
    def __init__(self):
        yaml.constructor.SafeConstructor.__init__(self)

    def construct_undefined(self, node):
        data = getattr(self, 'construct_' + node.id)(node)
        datatype = type(data)
        wraptype = type('TagWrap_'+datatype.__name__, (datatype,), {})
        wrapdata = wraptype(data)
        wrapdata.tag = lambda: None
        wrapdata.datatype = lambda: None
        setattr(wrapdata, "wrapTag", node.tag)
        setattr(wrapdata, "wrapType", datatype)
        return wrapdata


class SafeUnknownLoader(SafeUnknownConstructor, yaml.loader.SafeLoader):

    def __init__(self, stream):
        SafeUnknownConstructor.__init__(self)
        yaml.loader.SafeLoader.__init__(self, stream)


class SafeUnknownRepresenter(yaml.representer.SafeRepresenter):
    def represent_data(self, wrapdata):
        tag = False
        if type(wrapdata).__name__.startswith('TagWrap_'):
            datatype = getattr(wrapdata, "wrapType")
            tag = getattr(wrapdata, "wrapTag")
            data = datatype(wrapdata)
        else:
            data = wrapdata
        node = super(SafeUnknownRepresenter, self).represent_data(data)
        if tag:
            node.tag = tag
        return node

class SafeUnknownDumper(SafeUnknownRepresenter, yaml.dumper.SafeDumper):

    def __init__(self, stream,
            default_style=None, default_flow_style=False,
            canonical=None, indent=None, width=None,
            allow_unicode=None, line_break=None,
            encoding=None, explicit_start=None, explicit_end=None,
            version=None, tags=None, sort_keys=True):

        SafeUnknownRepresenter.__init__(self, default_style=default_style,
                default_flow_style=default_flow_style, sort_keys=sort_keys)

        yaml.dumper.SafeDumper.__init__(self,  stream,
                                        default_style=default_style,
                                        default_flow_style=default_flow_style,
                                        canonical=canonical,
                                        indent=indent,
                                        width=width,
                                        allow_unicode=allow_unicode,
                                        line_break=line_break,
                                        encoding=encoding,
                                        explicit_start=explicit_start,
                                        explicit_end=explicit_end,
                                        version=version,
                                        tags=tags,
                                        sort_keys=sort_keys)


MySafeLoader = SafeUnknownLoader
yaml.constructor.SafeConstructor.add_constructor(None, SafeUnknownConstructor.construct_undefined)