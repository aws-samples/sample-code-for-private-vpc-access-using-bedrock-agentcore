#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { CampaignRdsStack } from './rds-stack';

const app = new cdk.App();

new CampaignRdsStack(app, 'CampaignRdsStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: 'us-east-1',
  },
});

app.synth();
