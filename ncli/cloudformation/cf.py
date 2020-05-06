import click
import functools
import boto3
import yaml
import json
import subprocess

from .colors import colors

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

session = {}
yaml_configs = {}

def common_params(func):
    @click.option('--region', 'region', help="AWS region")
    @click.option('--profile', 'profile', help="AWS profile name")
    @click.option('-e', '--environment', 'env', default='dev', show_default=True, help="The environment for the stack")
    @click.argument('location', default='.')
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
        kwargs['stack_name'] = _getConfiguration('stack_name', kwargs['env'])

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
    command = ['aws', 's3', 'sync', '.', 's3://{bucket}/{key}'.format(bucket=kwargs['bucket'], key=key) ,'--exclude', '*', '--include', '*.yml', '--acl', 'bucket-owner-full-control']

    _printInfo(Bucket=kwargs['bucket'], Key=key)
    _executeAwsCliCommand(command, kwargs)

@cf.command()
@common_params
@click.option('-f', '--filename', 'filename', default='master.yml', show_default=True, help="File name of the master template")
def create(**kwargs):
    """Create CloudFormation Stack"""

    command = ['aws', 'cloudformation', 'create-stack', '--stack-name', kwargs['stack_name'] ,'--template-body', 'file://{}/{}'.format(kwargs['location'], kwargs['filename']), '--parameters', 'file://{}/{}'.format(kwargs['location'], kwargs['parameters']), '--capabilities', 'CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND']

    _printInfo(Stack=kwargs['stack_name'], Environment=kwargs['env'], Region=kwargs['region'], Bucket=kwargs['bucket'])
    _executeAwsCliCommand(command, kwargs)

@cf.command()
@common_params
@click.option('-f', '--filename', 'filename', default='master.yml', show_default=True, help="File name of the master template")
def update(**kwargs):
    """Update CloudFormation Stack"""
    command = ['aws', 'cloudformation', 'update-stack', '--stack-name', kwargs['stack_name'] ,'--template-body', 'file://{}/{}'.format(kwargs['location'], kwargs['filename']), '--parameters', 'file://{}/{}'.format(kwargs['location'], kwargs['parameters']), '--capabilities', 'CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND']

    _printInfo(Stack=kwargs['stack_name'], Environment=kwargs['env'], Region=kwargs['region'], Bucket=kwargs['bucket'])
    _executeAwsCliCommand(command, kwargs)

@cf.command()
@common_params
@click.option('-f', '--filename', 'filename', default='master.yml', show_default=True, help="File name of the master template")
def info(**kwargs):
    """Print settings used by the CLI"""
    key = kwargs['stack_name'] + '/' + kwargs['env']
    _printInfo(Stack=kwargs['stack_name'], Environment=kwargs['env'], Region=kwargs['region'], Bucket=kwargs['bucket'], Key=key)


# ############################### Helper Methods ###############################

def _printInfo(**kwargs):
    message = ''
    for key, value in kwargs.items():
        message += colors['CYAN'] + key + ': ' + colors['BLUE'] + value + colors['CYAN'] +'; '
    message += colors['NORMAL'] + '\n'
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
    process = subprocess.Popen(command, stdout=subprocess.PIPE, universal_newlines=True)

    while True:
        output = process.stdout.readline()
        click.echo(output.strip())
        return_code = process.poll()
        if return_code is not None:
            for output in process.stdout.readlines():
                click.echo(output.strip())
            break