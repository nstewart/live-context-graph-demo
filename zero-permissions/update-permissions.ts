import { execSync } from 'child_process';
import { mkdtempSync, readFileSync, rmSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import pg from 'pg';
const { Client } = pg;

// Configuration from environment variables
const MZ_HOST = process.env.MZ_HOST || 'mz';
const MZ_PORT = process.env.MZ_PORT || '6875';
const MZ_USER = process.env.MZ_USER || 'materialize';
const MZ_PASSWORD = process.env.MZ_PASSWORD || 'materialize';
const MZ_DATABASE = process.env.MZ_DATABASE || 'materialize';

// Retry configuration
const MAX_RETRIES = 30;
const RETRY_DELAY_MS = 2000;

function getConnectionString(): string {
    return `postgresql://${MZ_USER}:${MZ_PASSWORD}@${MZ_HOST}:${MZ_PORT}/${MZ_DATABASE}`;
}

async function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function waitForPermissionsTable(): Promise<void> {
    const connectionString = getConnectionString();
    console.log(`Waiting for zero.permissions table to exist...`);
    console.log(`Connection: postgresql://${MZ_USER}:***@${MZ_HOST}:${MZ_PORT}/${MZ_DATABASE}`);

    for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
        const client = new Client({ connectionString });
        try {
            await client.connect();

            // Check if the zero.permissions table exists
            const result = await client.query(`
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'zero.permissions'
                );
            `);

            if (result.rows[0].exists) {
                console.log(`✓ zero.permissions table found on attempt ${attempt}`);
                await client.end();
                return;
            }

            console.log(`Attempt ${attempt}/${MAX_RETRIES}: Table not found, waiting ${RETRY_DELAY_MS}ms...`);
            await client.end();
        } catch (error) {
            console.log(`Attempt ${attempt}/${MAX_RETRIES}: Connection failed - ${error instanceof Error ? error.message : error}`);
            try { await client.end(); } catch {}
        }

        if (attempt < MAX_RETRIES) {
            await sleep(RETRY_DELAY_MS);
        }
    }

    throw new Error(`Timed out waiting for zero.permissions table after ${MAX_RETRIES} attempts`);
}

async function updatePermissions(): Promise<void> {
    let tempDir: string | undefined;

    try {
        // Step 1: Wait for the permissions table to be created by materialize-zero
        await waitForPermissionsTable();

        // Step 1b: Set RETAIN HISTORY on zero.permissions. The materialize-zero
        // sidecar subscribes to it as a system collection on every zero-cache
        // (re)connect. With the default 1s retention, any reconnect after a
        // brief gap hits OutOfBoundsTimestampError, which the sidecar surfaces
        // as `reset-required`, which sets resetRequired=true in zero_change
        // and traps zero-cache in an infinite AutoResetSignal loop.
        {
            const retentionClient = new Client({ connectionString: getConnectionString() });
            await retentionClient.connect();
            console.log("Setting RETAIN HISTORY on zero.permissions...");
            await retentionClient.query(`ALTER TABLE "zero.permissions" SET (RETAIN HISTORY FOR '5 minutes')`);
            await retentionClient.end();
            console.log('✓ RETAIN HISTORY set on zero.permissions.');
        }

        // Step 2: Create a temp directory
        tempDir = mkdtempSync(join(tmpdir(), 'permissions-'));
        const outputFile = join(tempDir, 'perm.json');

        // Step 3: Run the `npx zero-deploy-permissions` command
        console.log('Generating permissions...');
        execSync(`npx zero-deploy-permissions --output-format=json --output-file=${outputFile}`, {
            stdio: 'inherit',
        });

        // Step 4: Read the file and execute it against Materialize
        const perm = readFileSync(outputFile, 'utf-8');
        const connectionString = getConnectionString();

        const client = new Client({ connectionString });
        await client.connect();

        console.log('Updating permissions in Materialize...');
        await client.query(`DELETE FROM "zero.permissions"`);
        await client.query(`INSERT INTO "zero.permissions" VALUES ($1, NULL)`, [perm]);
        await client.end();

        console.log('✓ Permissions updated successfully.');
    } catch (error) {
        console.error('Error updating permissions:', error);
        process.exit(1);
    } finally {
        // Cleanup: Remove the temp directory
        if (tempDir) {
            rmSync(tempDir, { recursive: true, force: true });
        }
    }
}

updatePermissions();
