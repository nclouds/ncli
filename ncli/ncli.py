import click
import boto3
import functools
import yaml

from .cloudformation.cf import cf

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

# def _secure_constructor(loader, node):
#     print(loader)
#     print(isinstance(node, yaml.nodes.SequenceNode))
#     # value = loader.construct_scalar(node)
#     # print(value)
#     return 'yes'
# yaml.SafeLoader.add_constructor(u'!env', _secure_constructor)

def common_params(func):
    @click.option('--region', 'region', help="AWS region")
    @click.option('--profile', 'profile', help="AWS profile name")
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

@click.group(context_settings=CONTEXT_SETTINGS)
@common_params
@click.pass_context
def ncli(ctx, region, profile):
    # session = boto3.session.Session(region_name=region, profile_name=profile)
    click.echo('')
    pass

ncli.add_command(cf)