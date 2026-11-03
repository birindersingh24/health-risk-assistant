import { Injectable } from '@nestjs/common';
import { Pinecone, Index } from '@pinecone-database/pinecone';

type VisitMetadata = { patientId: string; visitDate: string; text: string };

@Injectable()
export class PineconeService {
  private readonly pc = new Pinecone(); // reads PINECONE_API_KEY
  private indexPromise?: Promise<Index<VisitMetadata>>;

  // Creates the index once (no-op if it exists) and reuses it
  private getIndex() {
    this.indexPromise ??= (async () => {
      await this.pc.indexes.create({
        name: 'patient-history',
        schema: {
          fields: {
            _values: { type: 'dense_vector', dimension: 384, metric: 'cosine' },
          },
        },
        deployment: {
          deploymentType: 'managed',
          cloud: 'aws',
          region: 'us-east-1',
        },
        waitUntilReady: true,
        suppressConflicts: true,
      });
      const { host } = await this.pc.indexes.describe('patient-history');
      return this.pc.index<VisitMetadata>({ host });
    })();
    return this.indexPromise;
  }

  async upsertVisits(visits: (VisitMetadata & { embedding: number[] })[]) {
    const index = await this.getIndex();
    for (let i = 0; i < visits.length; i += 100) {
      // batches of 100
      await index.upsert({
        records: visits.slice(i, i + 100).map((v) => ({
          id: `${v.patientId}-${v.visitDate}`, // stable ID: re-ingest overwrites, no duplicates
          values: v.embedding,
          metadata: {
            patientId: v.patientId,
            visitDate: v.visitDate,
            text: v.text,
          },
        })),
      });
    }
  }

  async search(vector: number[], topK = 5, patientId?: string) {
    const index = await this.getIndex();
    const res = await index.query({
      vector,
      topK,
      includeMetadata: true,
      ...(patientId && { filter: { patientId: { $eq: patientId } } }),
    });
    return res.matches;
  }
}
