# nClouds CLI

This repository contains command line utilities that streamline the process of working with AWS resources. It contains different modules that cover a specific workflow

## Installation

The CLI requires python3.6+ installed

```console
$ pip install git+ssh://git@github.com/nclouds/ncli.git
```

## Usage

You can check the *help* documentation for the CLI

```console
$ ncli --help
```

## Modules

### CloudFormation

This module is just a thin wrapper over the AWS CLI for some of the CloudFormation commands. Using the AWS CLI speeds up de process of managing infrastructur with CloudFormation, but sometimes those commands get quite large and some arguments are repetitive within the same project, so the `ncli cf` tool runs *aws cli* commands with some default arguments based on some standards and settings from a configuration file. *For more information about nClouds CloudFormation standards click [here](https://github.com/nclouds/cloudformation/blob/master/standards.md)

```console
$ ncli cf --help

Usage: ncli cf [OPTIONS] COMMAND [ARGS]...

  nClouds thin wrapper over the AWS CLI for CloudFormation

Options:
  -h, --help  Show this message and exit.

Commands:
  create  Create CloudFormation Stack
  info    Print settings used by the CLI
  sync    Sync CloudFormation templates to S3 bucket
  update  Update CloudFormation Stack
```

All the *ncli cf* commands accept optional parameters and a *LOCATION* and *EXTRA-ARGS* arguments. 

The location sets the context of the command, which specifies where is the root of the project and where the *master.yml* and *.config* files are. The default value is the current directory (`.`)

The extra-args are just raw *aws cli* arguments that are passed directly to the `aws cloudformation` command which gives flexibility when using the tool

```console
$ ncli cf create -e dev . -- --roleArn: arn:aws:iam::1234567890:role/cf-role
```

The `--` just indicates that the rest of the command should be treated literally, otherwise the dashes can cause ambiguity for the command

#### Standards

The tool is based on some standards and some settings on a *.config* file for some of the parameters. The config file has the following structure

```yml
global:
  stack_name: ncli-test # [REQUIRED] The base name of the CloudFormation stack
  bucket: ronaldo-nclouds # [REQUIRED] The S3 bucket to store the CloudFormation templates for the nested stacks
  region: us-west-1 # [OPTIONAL] The AWS region to use (maps directly to --region aws cli parameter)
  profile: nclouds-dev # [OPTIONAL] The AWS profile to use (maps directly to --profile aws cli parameter)
  parameters: dev.json # [OPTIONAL] The name of the parameters json file for the stack
  multi_region: false # [OPTIONAL] Appends the region name to the bucket name and parameter files; defaults to false

dev: # You can override any of the above settings for each of the environments that you have
  region: us-west-2
```

The following conventions are used (sticking to the nClouds [CloudFormation standards](https://github.com/nclouds/cloudformation/blob/master/standards.md)):

1. The Stack name is going to be composed of the base name in the configuration file and the environment: `<stack_name>-<environment>`
2. The tool is going to look for a `master.yml` in the current directory, althought those values can be overriden by the `--filename` and the `LOCATION` argument
3. The default parameters file is `<environment>.json`, depending on the environment, although this can be overriden by the *parameters* setting in the *.config* file
4. If the **multi_region** flag is enabled the region name is going to be appended to the bucket name and parameter files as follows
    - bucket name: `<bucket-name>-<region>`
    - parameters file: `<filename>-<region>.json`

    The reason for this is that sometimes the bucket where the artifacts are stored, has to be in the same region where you are deploying, that's the case for lambda functions. The bucket where the zip file containing the code resides, has to be in the same region where you are creating the lambda, in this cases if you are deploying the same templates into different regions you are going to need an S3 bucket in each region so we encourage you to create a bucket with the region appendend to the name.

    When you deploy the same templates into multiple regions, you are allowed to use the same environment, and in these cases you may have different parameters for the two regions (eg. The VPC id) so we also append the the region to the parameters filename if the *multi_region* flag is enabled

At the end the purpose of this tool is just to speed up the process of managing infrastructure with CloudFormation by reducing the lenght of the commands based on some standards and default values. The tool doesn't seek to replace the aws cli and that's why we try to keep the tool as clean and ligthweight as possible to keep compatibility assured, in fact all of the things that you can do with the tool, you can do them with the aws cli as well


