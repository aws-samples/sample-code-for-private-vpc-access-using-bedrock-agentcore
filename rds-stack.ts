import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import { Construct } from 'constructs';

export class CampaignRdsStack extends cdk.Stack {
  public readonly database: rds.DatabaseInstance;
  public readonly vpc: ec2.Vpc;
  public readonly dbSecurityGroup: ec2.SecurityGroup;
  public readonly mcpServerSecurityGroup: ec2.SecurityGroup;
  
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Create VPC with PRIVATE subnets only (no public subnets for security)
    // IMPORTANT: DNS hostnames and DNS support are REQUIRED for AgentCore VPC endpoints
    this.vpc = new ec2.Vpc(this, 'CampaignVPC', {
      availabilityZones: ['us-east-1x', 'us-east-1x'],
      natGateways: 0,
      // Enable DNS for VPC endpoint resolution (required by AgentCore)
      enableDnsHostnames: true,
      enableDnsSupport: true,
      subnetConfiguration: [
        {
          cidrMask: 24,
          name: 'private',
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
        },
      ],
    });

    // VPC Endpoints for AWS services (no NAT Gateway needed)
    this.vpc.addInterfaceEndpoint('SSMEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.SSM,
    });

    this.vpc.addInterfaceEndpoint('SecretsManagerEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
    });

    this.vpc.addInterfaceEndpoint('BedrockAgentCoreEndpoint', {
      service: new ec2.InterfaceVpcEndpointService(
        `com.amazonaws.${this.region}.bedrock-agentcore`,
        443
      ),
    });

    this.vpc.addInterfaceEndpoint('EcrApiEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.ECR,
    });

    this.vpc.addInterfaceEndpoint('EcrDkrEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
    });

    this.vpc.addGatewayEndpoint('S3Endpoint', {
      service: ec2.GatewayVpcEndpointAwsService.S3,
    });

    this.vpc.addInterfaceEndpoint('CloudWatchLogsEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
    });

    // Additional VPC Endpoints for SSM Session Manager
    this.vpc.addInterfaceEndpoint('SSMMessagesEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.SSM_MESSAGES,
    });

    this.vpc.addInterfaceEndpoint('EC2MessagesEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.EC2_MESSAGES,
    });

    // Database access instance (for setup and maintenance via SSM Session Manager)
    const dbAccessSecurityGroup = new ec2.SecurityGroup(this, 'DbAccessSecurityGroup', {
      vpc: this.vpc,
      description: 'Security group for database access instance',
      allowAllOutbound: true,
    });

    const dbAccessRole = new iam.Role(this, 'DbAccessRole', {
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore'),
      ],
    });

    const dbAccessInstance = new ec2.Instance(this, 'DbAccessInstance', {
      vpc: this.vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
      machineImage: ec2.MachineImage.latestAmazonLinux2023(),
      securityGroup: dbAccessSecurityGroup,
      role: dbAccessRole,
    });

    // Install PostgreSQL client on database access instance
    dbAccessInstance.userData.addCommands(
      'yum update -y',
      'yum install -y postgresql15'
    );

    // Security group for MCP Server (AgentCore Runtime)
    this.mcpServerSecurityGroup = new ec2.SecurityGroup(this, 'MCPServerSecurityGroup', {
      vpc: this.vpc,
      description: 'Security group for MCP Server on AgentCore Runtime',
      allowAllOutbound: false,
    });

    // MCP Server egress: only allow necessary outbound traffic
    this.mcpServerSecurityGroup.addEgressRule(
      ec2.Peer.ipv4(this.vpc.vpcCidrBlock),
      ec2.Port.tcp(443),
      'Allow HTTPS to VPC endpoints (SSM, Secrets Manager, ECR, etc.)'
    );
    this.mcpServerSecurityGroup.addEgressRule(
      ec2.Peer.ipv4(this.vpc.vpcCidrBlock),
      ec2.Port.tcp(5432),
      'Allow PostgreSQL to RDS'
    );

    // Security group for RDS
    this.dbSecurityGroup = new ec2.SecurityGroup(this, 'DatabaseSecurityGroup', {
      vpc: this.vpc,
      description: 'Security group for Campaign RDS instance',
      allowAllOutbound: false,
    });

    // Allow PostgreSQL access from MCP Server security group only
    this.dbSecurityGroup.addIngressRule(
      this.mcpServerSecurityGroup,
      ec2.Port.tcp(5432),
      'Allow PostgreSQL access from MCP Server'
    );

    // Allow PostgreSQL access from database access instance
    this.dbSecurityGroup.addIngressRule(
      dbAccessSecurityGroup,
      ec2.Port.tcp(5432),
      'Allow PostgreSQL access from database access instance'
    );

    // Create RDS instance in private subnet
    this.database = new rds.DatabaseInstance(this, 'CampaignDatabase', {
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_15,
      }),
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.T3,
        ec2.InstanceSize.MICRO
      ),
      vpc: this.vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
      },
      securityGroups: [this.dbSecurityGroup],
      databaseName: 'campaigndb',
      allocatedStorage: 20,
      storageType: rds.StorageType.GP3,
      credentials: rds.Credentials.fromGeneratedSecret('dbadmin'),
      backupRetention: cdk.Duration.days(7),
      deleteAutomatedBackups: true,
      removalPolicy: cdk.RemovalPolicy.SNAPSHOT,
      deletionProtection: true,
      publiclyAccessible: false,  // Private database
      storageEncrypted: true,
      preferredBackupWindow: '03:00-04:00',
      preferredMaintenanceWindow: 'sun:04:00-sun:05:00',
      enablePerformanceInsights: true,
      performanceInsightRetention: rds.PerformanceInsightRetention.DEFAULT,
      monitoringInterval: cdk.Duration.seconds(60),
      cloudwatchLogsExports: ['postgresql', 'upgrade'],
      autoMinorVersionUpgrade: true,
      multiAz: true,
    });

    // Enable automatic secret rotation (SEC-07)
    this.database.addRotationSingleUser({
      automaticallyAfter: cdk.Duration.days(30),
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
    });

    // CloudWatch alarms for RDS monitoring (SEC-15)
    new cloudwatch.Alarm(this, 'RdsCpuAlarm', {
      metric: this.database.metricCPUUtilization(),
      threshold: 80,
      evaluationPeriods: 3,
      alarmDescription: 'RDS CPU utilization above 80% for 15 minutes',
    });

    new cloudwatch.Alarm(this, 'RdsFreeStorageAlarm', {
      metric: this.database.metricFreeStorageSpace(),
      threshold: 2 * 1024 * 1024 * 1024, // 2 GB
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.LESS_THAN_OR_EQUAL_TO_THRESHOLD,
      alarmDescription: 'RDS free storage below 2 GB',
    });

    new cloudwatch.Alarm(this, 'RdsConnectionsAlarm', {
      metric: this.database.metricDatabaseConnections(),
      threshold: 50,
      evaluationPeriods: 3,
      alarmDescription: 'RDS connections above 50 for 15 minutes (t3.micro max ~80)',
    });

    // Store only essential outputs in Parameter Store
    // Note: Use Fn.join for subnet IDs to ensure proper CloudFormation resolution
    new ssm.StringParameter(this, 'PrivateSubnetIdsParam', {
      parameterName: '/campaign/private-subnet-ids',
      stringValue: cdk.Fn.join(',', this.vpc.selectSubnets({
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED
      }).subnetIds),
    });

    new ssm.StringParameter(this, 'MCPServerSecurityGroupIdParam', {
      parameterName: '/campaign/mcp-sg-id',
      stringValue: this.mcpServerSecurityGroup.securityGroupId,
    });

    new ssm.StringParameter(this, 'DBEndpointParam', {
      parameterName: '/campaign/db-endpoint',
      stringValue: this.database.dbInstanceEndpointAddress,
    });

    new ssm.StringParameter(this, 'DBSecretArnParam', {
      parameterName: '/campaign/db-credentials-arn',
      stringValue: this.database.secret?.secretArn || 'N/A',
    });

    new ssm.StringParameter(this, 'DbAccessInstanceIdParam', {
      parameterName: '/campaign/db-access-instance-id',
      stringValue: dbAccessInstance.instanceId,
    });

    // Resource tags (M8)
    cdk.Tags.of(this).add('Project', 'amazon-ads-campaign-mcp');
    cdk.Tags.of(this).add('Environment', 'workshop');
  }
}
