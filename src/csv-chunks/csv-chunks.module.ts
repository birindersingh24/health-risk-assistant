import { Module } from '@nestjs/common';
import { CsvChunkController } from './csv-chunks.controller.js';
import { CsvChunkService } from './csv-chunks.service.js';
import { PineconeService } from '../vectorService.js';

@Module({
  controllers: [CsvChunkController],
  providers: [CsvChunkService, PineconeService],
})
export class CsvChunksModule {}
